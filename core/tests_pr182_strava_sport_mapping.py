"""
core/tests_pr182_strava_sport_mapping.py

PR-182 Bug #41a: Strava sport mapping expansion + decide_activity_creation relaxation.

Eight tests:
  T1 — WeightTraining → STRENGTH
  T2 — Yoga → STRENGTH
  T3 — Swim → SWIM
  T4 — Hike → WALK
  T5 — Unknown sport (Golf) → OTHER; duration>0, distance=0 → should_create=True
  T6 — RUN with distance=0 → should_create=False
  T7 — STRENGTH duration=1800, distance=0 → should_create=True
  T8 — Integration: STRENGTH activity + FUERZA PlannedWorkout → find_best_match returns it

Imports from integrations.strava are lazy (inside each test) per Law 4 / repo convention.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

User = get_user_model()


def _raw(sport_type):
    return {"sport_type": sport_type}


class StravaSportMappingTests(TestCase):

    # ── T1 ────────────────────────────────────────────────────────────────────

    def test_weighttraining_maps_to_strength(self):
        from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415
        self.assertEqual(_normalize_strava_sport_type(_raw("WeightTraining")), "STRENGTH")

    # ── T2 ────────────────────────────────────────────────────────────────────

    def test_yoga_maps_to_strength(self):
        from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415
        self.assertEqual(_normalize_strava_sport_type(_raw("Yoga")), "STRENGTH")

    # ── T3 ────────────────────────────────────────────────────────────────────

    def test_swim_maps_to_swim(self):
        from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415
        self.assertEqual(_normalize_strava_sport_type(_raw("Swim")), "SWIM")

    # ── T4 ────────────────────────────────────────────────────────────────────

    def test_hike_maps_to_walk(self):
        from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415
        self.assertEqual(_normalize_strava_sport_type(_raw("Hike")), "WALK")

    # ── T5 ────────────────────────────────────────────────────────────────────

    def test_unknown_sport_maps_to_other_and_is_created(self):
        from integrations.strava.normalizer import (  # noqa: PLC0415
            _normalize_strava_sport_type,
            decide_activity_creation,
        )
        self.assertEqual(_normalize_strava_sport_type(_raw("Golf")), "OTHER")
        normalized = {
            "tipo_deporte": "OTHER",
            "duracion": 1800,
            "distancia": 0.0,
        }
        decision = decide_activity_creation(normalized=normalized)
        self.assertTrue(decision.should_create, msg=f"Expected should_create=True, reason={decision.reason}")

    # ── T6 ────────────────────────────────────────────────────────────────────

    def test_run_with_zero_distance_not_created(self):
        from integrations.strava.normalizer import decide_activity_creation  # noqa: PLC0415
        normalized = {
            "tipo_deporte": "RUN",
            "duracion": 1800,
            "distancia": 0.0,
        }
        decision = decide_activity_creation(normalized=normalized)
        self.assertFalse(decision.should_create)
        self.assertIn("distance_non_positive", decision.reason)

    # ── T7 ────────────────────────────────────────────────────────────────────

    def test_strength_duration_only_is_created(self):
        from integrations.strava.normalizer import decide_activity_creation  # noqa: PLC0415
        normalized = {
            "tipo_deporte": "STRENGTH",
            "duracion": 1800,
            "distancia": 0.0,
        }
        decision = decide_activity_creation(normalized=normalized)
        self.assertTrue(decision.should_create, msg=f"Expected should_create=True, reason={decision.reason}")

    # ── T8 ────────────────────────────────────────────────────────────────────

    def test_strength_activity_matches_fuerza_plan(self):
        """STRENGTH activity + strength PlannedWorkout same day → find_best_match returns it."""
        from core.models import (  # noqa: PLC0415
            Athlete,
            Alumno,
            Coach,
            CompletedActivity,
            Membership,
            Organization,
            PlannedWorkout,
            WorkoutAssignment,
            WorkoutLibrary,
        )
        from core.services_reconciliation import find_best_match  # noqa: PLC0415

        # Setup
        coach_user = User.objects.create_user(username="str_coach_182", password="x")
        athlete_user = User.objects.create_user(username="str_athlete_182", password="x")
        org = Organization.objects.create(name="StrOrg182", slug="strorg182")
        Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)
        Membership.objects.create(user=athlete_user, organization=org, role="athlete", is_active=True)
        coach = Coach.objects.create(user=coach_user, organization=org)
        athlete = Athlete.objects.create(user=athlete_user, organization=org)
        alumno = Alumno.objects.create(entrenador=coach_user, usuario=athlete_user, nombre="S", apellido="T")

        library = WorkoutLibrary.objects.create(organization=org, name="Lib182")
        pw = PlannedWorkout.objects.create(
            organization=org,
            library=library,
            name="Fuerza semana 1",
            discipline="strength",
            session_type="base",
            estimated_duration_seconds=1800,
        )
        scheduled_date = datetime.date(2026, 4, 15)
        assignment = WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=pw,
            scheduled_date=scheduled_date,
            day_order=1,
        )
        activity = CompletedActivity.objects.create(
            organization=org,
            alumno=alumno,
            athlete=athlete,
            sport="STRENGTH",
            start_time=timezone.make_aware(datetime.datetime(2026, 4, 15, 9, 0, 0)),
            duration_s=1800,
            distance_m=0.0,
            provider="manual",
            provider_activity_id="pr182_strength_test_001",
        )

        matched, confidence, reason = find_best_match(assignment)
        self.assertIsNotNone(matched, msg=f"Expected a match; reason={reason}")
        self.assertEqual(matched.pk, activity.pk)
        self.assertGreaterEqual(confidence, 1.0)


# ── PR-184 regression tests ───────────────────────────────────────────────────


def test_strava_webhook_weight_training_maps_to_strength_via_ingest_flow():
    """PR-184 / PR-188d Bug #67: WeightTraining → STRENGTH via unified normalizer."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({"sport_type": "WeightTraining"}) == "STRENGTH"
    assert _normalize_strava_sport_type({"sport_type": "WEIGHTTRAINING"}) == "STRENGTH"
    assert _normalize_strava_sport_type({"sport_type": "WEIGHT_TRAINING"}) == "STRENGTH"


# ── PR-188d Fix 1 — Bike family unification ───────────────────────────────────


def test_ebike_ride_maps_to_bike():
    """Bug #67: EbikeRide must map to BIKE (was CYCLING → calendar showed OTHER)."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({"sport_type": "EbikeRide"}) == "BIKE"
    assert _normalize_strava_sport_type({"sport_type": "EBIKERIDE"}) == "BIKE"


def test_mountain_bike_ride_maps_to_bike():
    """Bug #67: MountainBikeRide must map to BIKE (was MTB → calendar showed OTHER)."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({"sport_type": "MountainBikeRide"}) == "BIKE"


def test_gravel_ride_maps_to_bike():
    """Bug #67: GravelRide must map to BIKE."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({"sport_type": "GravelRide"}) == "BIKE"
    assert _normalize_strava_sport_type({"sport_type": "GRAVELRIDE"}) == "BIKE"


def test_workout_maps_to_strength():
    """Bug #67: Workout (Strava gym) must map to STRENGTH (was CARDIO → OTHER)."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({"sport_type": "Workout"}) == "STRENGTH"


def test_none_sport_maps_to_other():
    """Bug #67: missing/empty sport_type falls back to OTHER."""
    from integrations.strava.normalizer import _normalize_strava_sport_type  # noqa: PLC0415

    assert _normalize_strava_sport_type({}) == "OTHER"
    assert _normalize_strava_sport_type({"sport_type": ""}) == "OTHER"
    assert _normalize_strava_sport_type({"sport_type": None}) == "OTHER"


def test_ingest_uses_normalizer_for_bike_family():
    """Bug #67: ingest call site maps EbikeRide → BIKE via unified normalizer."""
    from integrations.strava.services_strava_ingest import _resolve_sport  # noqa: PLC0415

    for strava_type in ("EbikeRide", "MountainBikeRide", "GravelRide", "Ride"):
        result = _resolve_sport(strava_type)
        assert result == "BIKE", f"Expected BIKE for {strava_type!r}, got {result!r}"


def test_resolve_sport_passes_through_canonical_business_codes():
    """tasks.py fallback: tipo_deporte already normalized (e.g. 'TRAIL') must pass through, not become OTHER."""
    from integrations.strava.services_strava_ingest import _resolve_sport  # noqa: PLC0415

    for code in ("RUN", "TRAIL", "BIKE", "SWIM", "WALK", "STRENGTH", "OTHER"):
        result = _resolve_sport(code)
        assert result == code, f"Passthrough failed for canonical code {code!r}: got {result!r}"
