"""
PR-135 — Suunto FIT ingestion: protective tests.

Coverage:
  1–5  parser.py  (FIT parsing, edge cases, missing data)
  6–8  services_suunto_ingest.py  (idempotency, validation)
  9–11 tasks.py  (fan-out, missing credential no-op)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fitparse_mock(session_fields: list[tuple[str, object]]):
    """
    Return a mock fitparse *module* whose FitFile yields one session message.

    Because parser.py does `import fitparse` lazily inside the function, we
    inject the mock via sys.modules so the `import` statement finds it there.
    """
    fields = [SimpleNamespace(name=name, value=value) for name, value in session_fields]
    message = MagicMock()
    message.__iter__ = MagicMock(return_value=iter(fields))
    mock_fit_instance = MagicMock()
    mock_fit_instance.get_messages.return_value = iter([message])

    mock_module = MagicMock()
    mock_module.FitFile.return_value = mock_fit_instance
    return mock_module


def _make_coach_and_alumno(suffix=""):
    from core.models import Alumno, Membership, Organization
    coach = User.objects.create_user(
        username=f"coach_suunto{suffix}", password="x"
    )
    slug = f"suunto-org{suffix}".lower()[:100]
    org = Organization.objects.create(name=f"SuuntoOrg{suffix}", slug=slug)
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    alumno = Alumno.objects.create(
        entrenador=coach, nombre="Athlete", apellido=f"Suunto{suffix}"
    )
    return coach, alumno


def _valid_fit_data(start: datetime | None = None) -> dict:
    return {
        "distance_m": 10000.0,
        "duration_s": 3600,
        "start_date": start or datetime(2026, 3, 16, 8, 0, 0, tzinfo=timezone.utc),
        "sport": "RUN",
        "elevation_gain_m": 150.0,
        "calories_kcal": 600.0,
        "avg_hr": 145.0,
        "name": "",
        "raw_summary": {"sport": "running"},
    }


# ---------------------------------------------------------------------------
# 1–5  Parser tests
# ---------------------------------------------------------------------------

class TestParseFitBytes:
    def test_parse_fit_bytes_basic(self):
        """FIT session fields are extracted into the normalized dict."""
        from integrations.suunto.parser import parse_fit_bytes

        start_dt = datetime(2026, 3, 16, 8, 0, 0, tzinfo=timezone.utc)
        mock_fitparse = _make_fitparse_mock([
            ("total_distance", 10000.0),
            ("total_elapsed_time", 3600.0),
            ("start_time", start_dt),
            ("sport", "running"),
            ("total_ascent", 150.0),
            ("total_calories", 600.0),
            ("avg_heart_rate", 145.0),
        ])

        with patch.dict(sys.modules, {"fitparse": mock_fitparse}):
            result = parse_fit_bytes(b"\x0e\x10FAKE_FIT")

        assert result["distance_m"] == 10000.0
        assert result["duration_s"] == 3600
        assert result["start_date"] == start_dt
        assert result["sport"] == "RUN"
        assert result["elevation_gain_m"] == 150.0
        assert result["calories_kcal"] == 600.0
        assert result["avg_hr"] == 145.0

    def test_parse_fit_bytes_empty_raises(self):
        """Empty bytes input must raise ValueError immediately."""
        from integrations.suunto.parser import parse_fit_bytes

        with pytest.raises(ValueError, match="empty bytes"):
            parse_fit_bytes(b"")

    def test_parse_fit_bytes_corrupted_raises(self):
        """Unparseable FIT data must raise ValueError (not crash silently)."""
        from integrations.suunto.parser import parse_fit_bytes

        mock_fitparse = MagicMock()
        mock_fitparse.FitFile.side_effect = Exception("bad header")
        with patch.dict(sys.modules, {"fitparse": mock_fitparse}):
            with pytest.raises(ValueError, match="failed to parse FIT data"):
                parse_fit_bytes(b"garbage")

    def test_parse_fit_bytes_missing_elevation_returns_none(self):
        """elevation_gain_m is None when total_ascent is absent from FIT."""
        from integrations.suunto.parser import parse_fit_bytes

        start_dt = datetime(2026, 3, 16, 9, 0, 0, tzinfo=timezone.utc)
        mock_fitparse = _make_fitparse_mock([
            ("total_distance", 5000.0),
            ("total_elapsed_time", 1800.0),
            ("start_time", start_dt),
        ])
        with patch.dict(sys.modules, {"fitparse": mock_fitparse}):
            result = parse_fit_bytes(b"\x0e\x10FAKE")

        assert result["elevation_gain_m"] is None

    def test_parse_fit_bytes_missing_calories_returns_none(self):
        """calories_kcal is None when total_calories is absent from FIT."""
        from integrations.suunto.parser import parse_fit_bytes

        mock_fitparse = _make_fitparse_mock([
            ("total_distance", 5000.0),
            ("total_elapsed_time", 1800.0),
            ("start_time", datetime(2026, 3, 16, 9, 0, 0, tzinfo=timezone.utc)),
        ])
        with patch.dict(sys.modules, {"fitparse": mock_fitparse}):
            result = parse_fit_bytes(b"\x0e\x10FAKE")

        assert result["calories_kcal"] is None


# ---------------------------------------------------------------------------
# 6–8  Ingestion service tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIngestSuuntoWorkout:
    def test_ingest_creates_completed_activity(self):
        """A new workout creates one CompletedActivity row."""
        from core.models import CompletedActivity
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        _, alumno = _make_coach_and_alumno("_create")
        activity, created = ingest_suunto_workout(
            alumno_id=alumno.pk,
            external_workout_id="wk-001",
            fit_data=_valid_fit_data(),
        )

        assert created is True
        assert CompletedActivity.objects.filter(
            provider="suunto", provider_activity_id="wk-001"
        ).count() == 1
        assert activity.distance_m == 10000.0

    def test_ingest_is_idempotent(self):
        """Calling ingest twice for the same workout produces exactly 1 row."""
        from core.models import CompletedActivity
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        _, alumno = _make_coach_and_alumno("_idem")
        fit = _valid_fit_data()

        a1, created1 = ingest_suunto_workout(alumno_id=alumno.pk, external_workout_id="wk-002", fit_data=fit)
        a2, created2 = ingest_suunto_workout(alumno_id=alumno.pk, external_workout_id="wk-002", fit_data=fit)

        assert created1 is True
        assert created2 is False
        assert a1.pk == a2.pk
        assert CompletedActivity.objects.filter(
            provider="suunto", provider_activity_id="wk-002"
        ).count() == 1

    def test_ingest_missing_start_date_raises(self):
        """fit_data without start_date must raise ValueError — never persist."""
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        _, alumno = _make_coach_and_alumno("_nodate")
        bad_fit = {**_valid_fit_data(), "start_date": None}

        with pytest.raises(ValueError, match="missing 'start_date'"):
            ingest_suunto_workout(alumno_id=alumno.pk, external_workout_id="wk-003", fit_data=bad_fit)


# ---------------------------------------------------------------------------
# 9–11  Task tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSuuntoTasks:
    def test_sync_athlete_workouts_fans_out(self):
        """sync_athlete_workouts calls ingest_workout.delay once per workout."""
        from core.models import OAuthCredential
        from integrations.suunto import tasks as suunto_tasks

        coach, alumno = _make_coach_and_alumno("_fanout")
        OAuthCredential.objects.create(
            alumno=alumno,
            provider="suunto",
            external_user_id="user123",
            access_token="tok",
        )

        workouts = [{"workoutKey": "wk-A"}, {"workoutKey": "wk-B"}]

        # list_workouts is imported lazily inside the task — patch the source module.
        # ingest_workout is a module-level attribute on tasks — patch its .delay.
        with (
            patch("integrations.suunto.client.list_workouts", return_value=workouts),
            patch.object(suunto_tasks.ingest_workout, "delay") as mock_delay,
        ):
            suunto_tasks.sync_athlete_workouts(alumno_id=alumno.pk, days_back=7)

        assert mock_delay.call_count == 2
        called_keys = {c.kwargs["external_workout_id"] for c in mock_delay.call_args_list}
        assert called_keys == {"wk-A", "wk-B"}

    def test_sync_athlete_workouts_no_credential_skips(self):
        """sync_athlete_workouts exits silently when no OAuthCredential exists."""
        from integrations.suunto import tasks as suunto_tasks

        _, alumno = _make_coach_and_alumno("_nocred_sync")

        with patch("integrations.suunto.client.list_workouts") as mock_list:
            suunto_tasks.sync_athlete_workouts(alumno_id=alumno.pk, days_back=7)

        mock_list.assert_not_called()

    def test_ingest_workout_no_credential_skips(self):
        """ingest_workout exits silently when no OAuthCredential exists."""
        from integrations.suunto import tasks as suunto_tasks

        _, alumno = _make_coach_and_alumno("_nocred_ingest")

        with patch("integrations.suunto.client.download_fit_file") as mock_dl:
            suunto_tasks.ingest_workout(alumno_id=alumno.pk, external_workout_id="wk-X")

        mock_dl.assert_not_called()
