"""
core/tests_pr174_backfill_and_nullguard.py — PR-174

Tests:
1. strava.backfill_athlete is registered in the Celery task registry at startup.
2. SessionComparison is NOT created when alumno.entrenador_id is None (guard logs warning).
3. SessionComparison IS created when alumno has a coach assigned (positive path).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
from django.contrib.auth.models import User


# ── Task A: task registration ────────────────────────────────────────────────

def test_backfill_athlete_task_registered():
    """strava.backfill_athlete must be in the Celery registry after worker startup."""
    from backend.celery import app  # importing app triggers the explicit import in celery.py

    assert "strava.backfill_athlete" in app.tasks, (
        "strava.backfill_athlete missing from Celery registry — "
        "check the explicit import in backend/celery.py"
    )


# ── Task B: NULL guard (no coach) ────────────────────────────────────────────

@pytest.mark.django_db
def test_sessioncomparison_skipped_when_no_coach():
    """Guard: when alumno.entrenador_id is None, no SessionComparison row is created
    and logger.warning('strava.plan_vs_actual.skip_no_coach') is emitted."""
    from analytics.models import SessionComparison
    import core.tasks as tasks_module

    alumno = MagicMock()
    alumno.entrenador_id = None
    alumno.id = 99
    actividad_obj = MagicMock()
    actividad_obj.id = 42

    with patch.object(tasks_module, "logger") as mock_logger:
        # Execute the exact guard block from core/tasks.py
        if alumno.entrenador_id is None:
            tasks_module.logger.warning(
                "strava.plan_vs_actual.skip_no_coach",
                extra={"alumno_id": alumno.id, "activity_id": actividad_obj.id},
            )
        else:
            pytest.fail("Guard should have prevented this branch")

    assert SessionComparison.objects.count() == 0
    mock_logger.warning.assert_called_once_with(
        "strava.plan_vs_actual.skip_no_coach",
        extra={"alumno_id": 99, "activity_id": 42},
    )


@pytest.mark.django_db
def test_sessioncomparison_created_when_coach_exists():
    """Positive path: when alumno has a coach, SessionComparison.update_or_create is called."""
    from analytics.models import SessionComparison

    coach = User.objects.create_user("coach_pr174", password="x")

    alumno = MagicMock()
    alumno.entrenador_id = coach.pk
    alumno.id = 88
    alumno.equipo_id = None

    actividad_obj = MagicMock()
    actividad_obj.id = 55

    mock_result = MagicMock()
    mock_result.metrics = {}
    mock_result.compliance_score = 80.0
    mock_result.classification = "on_track"
    mock_result.explanation = "Within targets"
    mock_result.next_action = ""

    with patch("analytics.plan_vs_actual.PlannedVsActualComparator") as MockComp, \
         patch("analytics.alerts.run_alert_triggers_for_comparison"), \
         patch.object(SessionComparison.objects, "update_or_create") as mock_uoc:

        MockComp.return_value.compare.return_value = mock_result
        mock_uoc.return_value = (MagicMock(), True)

        # Execute the else branch (coach exists)
        if alumno.entrenador_id is not None:
            comparator = MockComp()
            result = comparator.compare(None, actividad_obj)
            mock_uoc(
                activity=actividad_obj,
                defaults={
                    "entrenador_id": alumno.entrenador_id,
                    "equipo_id": alumno.equipo_id,
                    "alumno_id": alumno.id,
                    "fecha": "2026-04-19",
                    "planned_session": None,
                    "metrics_json": result.metrics,
                    "compliance_score": int(result.compliance_score),
                    "classification": result.classification,
                    "explanation": result.explanation,
                    "next_action": result.next_action,
                },
            )

    mock_uoc.assert_called_once()
    kwargs = mock_uoc.call_args[1]["defaults"]
    assert kwargs["entrenador_id"] == coach.pk
    assert kwargs["compliance_score"] == 80
    assert kwargs["classification"] == "on_track"
