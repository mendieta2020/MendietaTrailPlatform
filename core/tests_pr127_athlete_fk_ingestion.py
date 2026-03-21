"""
PR-127 — Ingestion pipeline fills CompletedActivity.athlete FK (D3 fix).

Coverage:
  1  Suunto ingestion fills athlete FK when Athlete row exists for the alumno
  2  Suunto ingestion leaves athlete=None when no Athlete exists (no failure)
  3  Second Suunto ingestion is idempotent — does not break athlete FK
  4  Cross-org: Athlete from a different org is NOT assigned
  5  Strava ingestion fills athlete FK when Athlete row exists for the alumno
  6  Strava ingestion leaves athlete=None when no Athlete exists (no failure)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

_T0 = datetime(2026, 3, 20, 7, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org_and_coach(suffix: str):
    from core.models import Membership, Organization
    coach = User.objects.create_user(username=f"coach127{suffix}", password="x")
    org = Organization.objects.create(name=f"Org127{suffix}", slug=f"org127{suffix}")
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    return org, coach


def _make_alumno(coach, *, with_user: bool = True, suffix: str = ""):
    from core.models import Alumno
    linked_user = None
    if with_user:
        linked_user = User.objects.create_user(username=f"ath127{suffix}", password="x")
    return Alumno.objects.create(
        entrenador=coach,
        nombre="Test",
        apellido=f"Athlete127{suffix}",
        usuario=linked_user,
    )


def _make_athlete(user, org):
    from core.models import Athlete
    return Athlete.objects.create(user=user, organization=org)


def _suunto_fit_data() -> dict:
    return {
        "distance_m": 10000.0,
        "duration_s": 3600,
        "start_date": _T0,
        "sport": "RUN",
        "elevation_gain_m": 100.0,
        "calories_kcal": 500.0,
        "avg_hr": 140.0,
        "name": "",
        "raw_summary": {},
    }


def _strava_activity_data() -> dict:
    return {
        "start_date_local": _T0,
        "elapsed_time_s": 3600,
        "distance_m": 10000.0,
        "type": "Run",
        "elevation_m": 100.0,
        "calories_kcal": 500.0,
        "avg_hr": 140.0,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# Test 1 — Suunto fills athlete FK when Athlete exists
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suunto_ingest_fills_athlete_fk_when_athlete_exists():
    from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

    org, coach = _make_org_and_coach("_s1")
    alumno = _make_alumno(coach, with_user=True, suffix="_s1")
    athlete = _make_athlete(alumno.usuario, org)

    activity, created = ingest_suunto_workout(
        alumno_id=alumno.pk,
        external_workout_id="pr127-suunto-001",
        fit_data=_suunto_fit_data(),
    )

    assert created is True
    activity.refresh_from_db()
    assert activity.athlete_id == athlete.pk


# ---------------------------------------------------------------------------
# Test 2 — Suunto leaves athlete=None when no Athlete row exists
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suunto_ingest_athlete_none_when_no_athlete_row():
    from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

    org, coach = _make_org_and_coach("_s2")
    # alumno has a linked user but NO Athlete row in DB
    alumno = _make_alumno(coach, with_user=True, suffix="_s2")

    activity, created = ingest_suunto_workout(
        alumno_id=alumno.pk,
        external_workout_id="pr127-suunto-002",
        fit_data=_suunto_fit_data(),
    )

    assert created is True
    activity.refresh_from_db()
    assert activity.athlete_id is None


# ---------------------------------------------------------------------------
# Test 3 — Suunto second ingestion is idempotent; athlete FK preserved
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suunto_ingest_idempotent_preserves_athlete_fk():
    from core.models import CompletedActivity
    from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

    org, coach = _make_org_and_coach("_s3")
    alumno = _make_alumno(coach, with_user=True, suffix="_s3")
    athlete = _make_athlete(alumno.usuario, org)

    a1, created1 = ingest_suunto_workout(
        alumno_id=alumno.pk,
        external_workout_id="pr127-suunto-003",
        fit_data=_suunto_fit_data(),
    )
    a2, created2 = ingest_suunto_workout(
        alumno_id=alumno.pk,
        external_workout_id="pr127-suunto-003",
        fit_data=_suunto_fit_data(),
    )

    assert created1 is True
    assert created2 is False
    assert a1.pk == a2.pk
    assert CompletedActivity.objects.filter(provider_activity_id="pr127-suunto-003").count() == 1
    a1.refresh_from_db()
    assert a1.athlete_id == athlete.pk


# ---------------------------------------------------------------------------
# Test 4 — Cross-org: Athlete from a different org is NOT assigned
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suunto_ingest_cross_org_athlete_not_assigned():
    from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

    # Primary org + alumno
    org, coach = _make_org_and_coach("_s4a")
    alumno = _make_alumno(coach, with_user=True, suffix="_s4")

    # Second org — Athlete exists there for the same user, but NOT in primary org
    org2, _ = _make_org_and_coach("_s4b")
    _make_athlete(alumno.usuario, org2)  # wrong org

    activity, created = ingest_suunto_workout(
        alumno_id=alumno.pk,
        external_workout_id="pr127-suunto-004",
        fit_data=_suunto_fit_data(),
    )

    assert created is True
    activity.refresh_from_db()
    # Must NOT pick up the Athlete from org2
    assert activity.athlete_id is None


# ---------------------------------------------------------------------------
# Test 5 — Strava fills athlete FK when Athlete exists
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_ingest_fills_athlete_fk_when_athlete_exists():
    from integrations.strava.services_strava_ingest import ingest_strava_activity

    org, coach = _make_org_and_coach("_r1")
    alumno = _make_alumno(coach, with_user=True, suffix="_r1")
    athlete = _make_athlete(alumno.usuario, org)

    activity, created = ingest_strava_activity(
        alumno_id=alumno.pk,
        external_activity_id="pr127-strava-001",
        activity_data=_strava_activity_data(),
    )

    assert created is True
    activity.refresh_from_db()
    assert activity.athlete_id == athlete.pk


# ---------------------------------------------------------------------------
# Test 6 — Strava leaves athlete=None when no Athlete row exists
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_ingest_athlete_none_when_no_athlete_row():
    from integrations.strava.services_strava_ingest import ingest_strava_activity

    org, coach = _make_org_and_coach("_r2")
    # alumno has linked user but NO Athlete row
    alumno = _make_alumno(coach, with_user=True, suffix="_r2")

    activity, created = ingest_strava_activity(
        alumno_id=alumno.pk,
        external_activity_id="pr127-strava-002",
        activity_data=_strava_activity_data(),
    )

    assert created is True
    activity.refresh_from_db()
    assert activity.athlete_id is None
