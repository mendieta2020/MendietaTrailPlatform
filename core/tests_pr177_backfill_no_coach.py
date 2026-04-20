"""
core/tests_pr177_backfill_no_coach.py — PR-177

Tests:
1. Backfill skips activity gracefully when alumno has no coach (no crash).
2. strava.ingest.skip_no_coach structured event is logged per skipped activity.
3. Regression: backfill ingests correctly when coach + membership are present.
4. Exception handler uses logger.exception with exc_info=True (full traceback).
5. Result dict reflects correct created/skipped/errors counts with mixed outcomes.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_summary_activity(strava_id: int = 1001) -> dict:
    return {
        "id": strava_id,
        "sport_type": "Run",
        "type": "Run",
        "start_date_local": "2026-01-10T08:00:00Z",
        "start_date": "2026-01-10T08:00:00Z",
        "elapsed_time": 3600,
        "distance": 10000.0,
        "total_elevation_gain": 50.0,
        "calories": None,
        "average_heartrate": None,
    }


def _patched_requests_get(activities_pages):
    """Return a mock that yields pages of activities then an empty list."""
    call_count = [0]
    pages = list(activities_pages) + [[]]

    def _get(*args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = pages[min(call_count[0], len(pages) - 1)]
        call_count[0] += 1
        return resp

    return _get


# ── Test 1: no-coach guard — no crash ────────────────────────────────────────

@pytest.mark.django_db
def test_backfill_skips_activity_when_no_coach_assigned():
    """
    When _derive_organization returns None (no coach, no Athlete fallback),
    backfill_strava_activities must complete without raising and return errors=0.
    """
    from django.contrib.auth.models import User
    from core.models import Alumno
    from integrations.strava.services_strava_ingest import backfill_strava_activities

    alumno = Alumno.objects.create(entrenador=None)
    activities = [_make_summary_activity(1001), _make_summary_activity(1002)]

    with patch("requests.get", side_effect=_patched_requests_get([activities])):
        result = backfill_strava_activities(
            alumno_id=alumno.pk,
            access_token="fake-token",
            days=30,
        )

    assert result["errors"] == 0, "No errors expected — skip is graceful"
    assert result["created"] == 0
    assert result["skipped"] == 2


# ── Test 2: skip event is logged with context ────────────────────────────────

@pytest.mark.django_db
def test_backfill_logs_skip_event_with_context():
    """
    For each skipped activity, strava.ingest.skip_no_coach must be logged
    with alumno_id and strava_activity_id in extra.
    """
    from core.models import Alumno
    import integrations.strava.services_strava_ingest as ingest_module

    alumno = Alumno.objects.create(entrenador=None)
    activities = [_make_summary_activity(2001)]

    with patch("requests.get", side_effect=_patched_requests_get([activities])), \
         patch.object(ingest_module, "logger") as mock_log:

        backfill_strava_activities = ingest_module.backfill_strava_activities
        backfill_strava_activities(
            alumno_id=alumno.pk,
            access_token="fake-token",
            days=30,
        )

    calls = [c for c in mock_log.info.call_args_list
             if c.args and c.args[0] == "strava.ingest.skip_no_coach"]
    assert len(calls) == 1
    extra = calls[0].kwargs["extra"]
    assert extra["alumno_id"] == alumno.pk
    assert extra["strava_activity_id"] == 2001
    assert extra["reason_code"] == "NO_ORGANIZATION_RESOLVED"


# ── Test 3: regression — ingests when coach + membership present ──────────────

@pytest.mark.django_db
def test_backfill_ingests_when_coach_present_and_membership_active():
    """
    Positive path: alumno with an active coach membership produces created=1.
    """
    from django.contrib.auth.models import User
    from core.models import Alumno, Organization, Membership, CompletedActivity
    from integrations.strava.services_strava_ingest import backfill_strava_activities

    coach = User.objects.create_user("coach_pr177", password="x")
    org = Organization.objects.create(name="Org PR177")
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    alumno = Alumno.objects.create(entrenador=coach)

    activities = [_make_summary_activity(3001)]

    with patch("requests.get", side_effect=_patched_requests_get([activities])), \
         patch("core.tasks.compute_pmc_for_activity") as mock_pmc:
        mock_pmc.delay = MagicMock()
        result = backfill_strava_activities(
            alumno_id=alumno.pk,
            access_token="fake-token",
            days=30,
        )

    assert result["created"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert CompletedActivity.objects.filter(
        organization=org, provider_activity_id="3001"
    ).exists()


# ── Test 3b: ambiguous org (multiple Athlete rows) → None, fail-closed ───────

@pytest.mark.django_db
def test_derive_organization_returns_none_when_multiple_athletes():
    """
    Law 1 fail-closed: when a user has Athlete rows in multiple orgs,
    _derive_organization must return None and log strava.ingest.ambiguous_org_fallback.
    """
    from django.contrib.auth.models import User
    from core.models import Alumno, Organization, Athlete
    import integrations.strava.services_strava_ingest as ingest_module

    user = User.objects.create_user("athlete_multiorg_pr177", password="x")
    alumno = Alumno.objects.create(entrenador=None, usuario=user)
    org1 = Organization.objects.create(name="Org A PR177", slug="org-a-pr177")
    org2 = Organization.objects.create(name="Org B PR177", slug="org-b-pr177")
    Athlete.objects.create(organization=org1, user=user)
    Athlete.objects.create(organization=org2, user=user)

    with patch.object(ingest_module, "logger") as mock_log:
        alumno_obj = Alumno.objects.select_related("entrenador").get(pk=alumno.pk)
        result = ingest_module._derive_organization(alumno_obj)

    assert result is None
    warning_events = [
        c for c in mock_log.warning.call_args_list
        if c.args and c.args[0] == "strava.ingest.ambiguous_org_fallback"
    ]
    assert len(warning_events) == 1
    assert warning_events[0].kwargs["extra"]["org_count"] == 2


# ── Test 4: logger.exception with exc_info=True on activity error ─────────────

@pytest.mark.django_db
def test_backfill_logger_exception_includes_traceback():
    """
    When ingest_strava_activity raises, logger.exception must be called
    (not logger.warning) so the full traceback appears in structured logs.
    """
    from django.contrib.auth.models import User
    from core.models import Alumno, Organization, Membership
    import integrations.strava.services_strava_ingest as ingest_module

    coach = User.objects.create_user("coach_pr177b", password="x")
    org = Organization.objects.create(name="Org PR177b")
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    alumno = Alumno.objects.create(entrenador=coach)

    activities = [_make_summary_activity(4001)]

    with patch("requests.get", side_effect=_patched_requests_get([activities])), \
         patch.object(ingest_module, "ingest_strava_activity",
                      side_effect=RuntimeError("db exploded")), \
         patch.object(ingest_module, "logger") as mock_log:

        ingest_module.backfill_strava_activities(
            alumno_id=alumno.pk,
            access_token="fake-token",
            days=30,
        )

    # logger.exception captures exc_info implicitly — assert it was used (not logger.warning).
    mock_log.exception.assert_called_once()
    mock_log.warning.assert_not_called()
    extra = mock_log.exception.call_args.kwargs["extra"]
    assert extra["strava_activity_id"] == 4001
    assert extra["alumno_id"] == alumno.pk


# ── Test 5: mixed outcomes — correct result structure ────────────────────────

@pytest.mark.django_db
def test_backfill_result_structure_with_mixed_outcomes():
    """
    When backfill processes activities with mixed results (created / skipped /
    errors), the result dict must accurately reflect all three counters.
    """
    from django.contrib.auth.models import User
    from core.models import Alumno, Organization, Membership
    import integrations.strava.services_strava_ingest as ingest_module

    coach = User.objects.create_user("coach_pr177c", password="x")
    org = Organization.objects.create(name="Org PR177c")
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    alumno = Alumno.objects.create(entrenador=coach)

    activities = [
        _make_summary_activity(5001),
        _make_summary_activity(5002),
        _make_summary_activity(5003),
    ]

    results_seq = [
        (MagicMock(), True),   # 5001 → created
        (MagicMock(), False),  # 5002 → skipped (duplicate)
    ]
    call_idx = [0]

    def _ingest_side(**kwargs):
        if kwargs["external_activity_id"] == "5003":
            raise ValueError("bad data")
        result = results_seq[call_idx[0]]
        call_idx[0] += 1
        return result

    with patch("requests.get", side_effect=_patched_requests_get([activities])), \
         patch.object(ingest_module, "ingest_strava_activity", side_effect=_ingest_side):
        result = ingest_module.backfill_strava_activities(
            alumno_id=alumno.pk,
            access_token="fake-token",
            days=30,
        )

    assert result == {"created": 1, "skipped": 1, "errors": 1}
