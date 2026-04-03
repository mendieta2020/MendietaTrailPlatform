"""
core/tests_pr159_athlete_card.py

PR-159: Athlete Card — coach reads/writes profile, injuries, goals, notes.

Coverage (8 tests):
  1. coach_can_read_athlete_profile
  2. coach_can_patch_athlete_profile_weight_and_fc
  3. coach_cannot_read_profile_of_athlete_in_different_org
  4. coach_can_list_athlete_injuries
  5. coach_can_create_injury_for_athlete
  6. coach_can_list_athlete_goals
  7. coach_can_read_and_write_coach_notes
  8. athlete_cannot_access_coach_athlete_card_endpoints
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteGoal,
    AthleteInjury,
    AthleteProfile,
    Membership,
    Organization,
    WorkoutLibrary,
)

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active,
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_coach_can_read_athlete_profile():
    org = _org("org-read-profile")
    coach_user = _user("coach_rp")
    athlete_user = _user("athlete_rp")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)
    AthleteProfile.objects.create(
        organization=org,
        athlete=athlete,
        weight_kg=70.0,
        height_cm=175.0,
    )

    client = APIClient()
    client.force_authenticate(user=coach_user)
    res = client.get(f"/api/coach/athletes/{athlete_m.pk}/profile/")

    assert res.status_code == 200
    assert res.data["profile"]["weight_kg"] == 70.0
    assert res.data["athlete_email"] == athlete_user.email


@pytest.mark.django_db
def test_coach_can_patch_athlete_profile_weight_and_fc():
    org = _org("org-patch-profile")
    coach_user = _user("coach_pp")
    athlete_user = _user("athlete_pp")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)
    AthleteProfile.objects.create(organization=org, athlete=athlete)

    client = APIClient()
    client.force_authenticate(user=coach_user)
    res = client.patch(
        f"/api/coach/athletes/{athlete_m.pk}/profile/",
        {"weight_kg": 68.5, "max_hr_bpm": 185},
        format="json",
    )

    assert res.status_code == 200
    assert res.data["weight_kg"] == 68.5
    assert res.data["max_hr_bpm"] == 185


@pytest.mark.django_db
def test_coach_cannot_read_profile_of_athlete_in_different_org():
    org_a = _org("org-a-profile")
    org_b = _org("org-b-profile")
    coach_user = _user("coach_iso_p")
    athlete_user = _user("athlete_iso_p")
    _membership(coach_user, org_a, "coach")
    athlete_m = _membership(athlete_user, org_b, "athlete")
    _athlete(athlete_user, org_b)

    client = APIClient()
    client.force_authenticate(user=coach_user)
    res = client.get(f"/api/coach/athletes/{athlete_m.pk}/profile/")

    assert res.status_code == 404


@pytest.mark.django_db
def test_coach_can_list_athlete_injuries():
    org = _org("org-injuries")
    coach_user = _user("coach_inj")
    athlete_user = _user("athlete_inj")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)
    AthleteInjury.objects.create(
        organization=org,
        athlete=athlete,
        injury_type="muscular",
        body_zone="muslo",
        severity="leve",
        date_occurred=datetime.date.today(),
        status="activa",
    )

    client = APIClient()
    client.force_authenticate(user=coach_user)
    res = client.get(f"/api/coach/athletes/{athlete_m.pk}/card-injuries/")

    assert res.status_code == 200
    assert res.data["count"] == 1
    assert res.data["results"][0]["body_zone"] == "muslo"


@pytest.mark.django_db
def test_coach_can_create_injury_for_athlete():
    org = _org("org-create-inj")
    coach_user = _user("coach_ci")
    athlete_user = _user("athlete_ci")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    _athlete(athlete_user, org)

    client = APIClient()
    client.force_authenticate(user=coach_user)
    payload = {
        "injury_type": "tendinosa",
        "body_zone": "tobillo",
        "severity": "moderada",
        "date_occurred": str(datetime.date.today()),
        "status": "activa",
    }
    res = client.post(
        f"/api/coach/athletes/{athlete_m.pk}/card-injuries/",
        payload,
        format="json",
    )

    assert res.status_code == 201
    assert AthleteInjury.objects.filter(
        organization=org, body_zone="tobillo"
    ).exists()


@pytest.mark.django_db
def test_coach_can_list_athlete_goals():
    org = _org("org-goals-card")
    coach_user = _user("coach_gc")
    athlete_user = _user("athlete_gc")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)
    AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        title="Patagonia Run",
        priority="A",
        status="active",
        target_date=datetime.date(2026, 11, 15),
        created_by=coach_user,
    )

    client = APIClient()
    client.force_authenticate(user=coach_user)
    res = client.get(f"/api/coach/athletes/{athlete_m.pk}/card-goals/")

    assert res.status_code == 200
    assert res.data["count"] == 1
    assert res.data["results"][0]["title"] == "Patagonia Run"


@pytest.mark.django_db
def test_coach_can_read_and_write_coach_notes():
    org = _org("org-notes")
    coach_user = _user("coach_notes")
    athlete_user = _user("athlete_notes")
    _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)

    client = APIClient()
    client.force_authenticate(user=coach_user)

    # Write
    res = client.put(
        f"/api/coach/athletes/{athlete_m.pk}/notes/",
        {"notes": "Needs extra recovery after long runs."},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["coach_notes"] == "Needs extra recovery after long runs."

    # Read back
    res2 = client.get(f"/api/coach/athletes/{athlete_m.pk}/notes/")
    assert res2.status_code == 200
    assert res2.data["coach_notes"] == "Needs extra recovery after long runs."

    # Verify persisted
    athlete.refresh_from_db()
    assert athlete.notes == "Needs extra recovery after long runs."


@pytest.mark.django_db
def test_athlete_cannot_access_coach_athlete_card_endpoints():
    org = _org("org-rbac-card")
    athlete_user = _user("athlete_rbac")
    athlete_m = _membership(athlete_user, org, "athlete")
    _athlete(athlete_user, org)

    client = APIClient()
    client.force_authenticate(user=athlete_user)
    res = client.get(f"/api/coach/athletes/{athlete_m.pk}/profile/")

    # Athlete has no coach membership — expect 403 or 404
    assert res.status_code in (403, 404)
