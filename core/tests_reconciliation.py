"""
core/tests_reconciliation.py

PR-118: Plan vs Real Reconciliation — comprehensive tests.

These tests validate the scientific brainstem of Quantoryn:
- Compliance scoring is deterministic and within 0..120
- Compliance categories are derived from centralized COMPLIANCE_RANGES
- Primary target variable drives the headline score
- Signals are generated correctly and deduplicated
- Auto-matching is confidence-aware and fail-closed on ambiguity
- Organization isolation is absolute
- Reconciliation is idempotent
- Plan ≠ Real invariant is preserved (neither planning nor execution model is mutated)
- Weekly adherence aggregation is correct

Coverage:
 1. perfect match — score 100, category "completed"
 2. under-compliance — score < 85, category "regular" or "not_completed"
 3. over-compliance — score > 100, capped at 120
 4. higher-than-prescribed pace — pace_out_of_target signal
 5. no activity for planned assignment — state=missed, score=0
 6. auto-match finds no candidate — state=unmatched
 7. ambiguous match (two activities) — fail-closed, state=ambiguous
 8. organization isolation — cross-org activity not matched
 9. weekly adherence correctness
10. score clamped at 0 (no execution data)
11. score clamped at 120 (enormous over-compliance)
12. compliance category boundary coverage
13. idempotent reconcile (no duplicate records)
14. Plan ≠ Real invariant (assignment and activity unchanged)
15. primary_target_variable explicit override
16. auto_match_and_reconcile creates RECONCILED record
17. no athlete FK on assignment → auto-match skips gracefully
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Alumno,
    Athlete,
    Coach,
    CompletedActivity,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
    WorkoutReconciliation,
)
from core.services_reconciliation import (
    AUTO_MATCH_CONFIDENCE_THRESHOLD,
    COMPLIANCE_RANGES,
    SCORE_MAX,
    SCORE_MIN,
    ComplianceSignal,
    auto_match_and_reconcile,
    compute_weekly_adherence,
    find_best_match,
    mark_assignment_missed,
    reconcile,
    score_compliance,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _make_coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _make_alumno(user, coach_user):
    return Alumno.objects.create(
        entrenador=coach_user,
        usuario=user,
        nombre="Test",
        apellido="Athlete",
    )


def _make_library(org, name="Default Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _make_planned_workout(org, library, **kwargs):
    defaults = {
        "name": "Test Workout",
        "discipline": "run",
        "session_type": "base",
        "estimated_duration_seconds": 3600,   # 60 min
        "estimated_distance_meters": 10000,   # 10 km
    }
    defaults.update(kwargs)
    return PlannedWorkout.objects.create(organization=org, library=library, **defaults)


def _make_assignment(org, athlete, planned_workout, scheduled_date=None, **kwargs):
    if scheduled_date is None:
        scheduled_date = datetime.date(2026, 4, 1)
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
        day_order=kwargs.pop("day_order", 1),
        **kwargs,
    )


_activity_counter = 0  # module-level counter for unique provider_activity_id generation


def _make_activity(coach_user, alumno, athlete, sport="RUN", duration_s=3600,
                   distance_m=10000.0, elevation_gain_m=None,
                   start_time=None, **kwargs):
    global _activity_counter
    _activity_counter += 1
    if start_time is None:
        start_time = timezone.make_aware(
            datetime.datetime(2026, 4, 1, 8, 0, 0)
        )
    return CompletedActivity.objects.create(
        organization=coach_user,   # legacy User FK (D2 debt)
        alumno=alumno,
        athlete=athlete,
        sport=sport,
        start_time=start_time,
        duration_s=duration_s,
        distance_m=distance_m,
        elevation_gain_m=elevation_gain_m,
        provider="manual",
        # Use a global counter to guarantee uniqueness across all test cases
        provider_activity_id=f"test_{_activity_counter}_{sport}_{start_time.timestamp():.0f}",
        **kwargs,
    )


# ==============================================================================
# Plan ≠ Real Invariant Tests
# (Named class so they can never be removed without a deliberate decision)
# ==============================================================================

class PlanNotRealInvariantTests(TestCase):
    """
    Asserts that reconciliation never mutates the planning or execution domain.

    These tests may never be removed to accommodate a feature request.
    A feature that requires their removal is architecturally wrong.
    """

    def setUp(self):
        self.coach_user = _make_user("inv_coach")
        self.org        = _make_org("InvOrg")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)
        self.athlete_user = _make_user("inv_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete  = _make_athlete(self.athlete_user, self.org)
        self.alumno   = _make_alumno(self.athlete_user, self.coach_user)
        self.library  = _make_library(self.org)
        self.workout  = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(self.org, self.athlete, self.workout)
        self.activity   = _make_activity(self.coach_user, self.alumno, self.athlete)

    def test_reconcile_does_not_modify_planned_workout(self):
        original_name     = self.workout.name
        original_duration = self.workout.estimated_duration_seconds
        reconcile(assignment=self.assignment, activity=self.activity)
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, original_name)
        self.assertEqual(self.workout.estimated_duration_seconds, original_duration)

    def test_reconcile_does_not_modify_completed_activity(self):
        original_duration_s = self.activity.duration_s
        original_distance_m = self.activity.distance_m
        reconcile(assignment=self.assignment, activity=self.activity)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.duration_s, original_duration_s)
        self.assertEqual(self.activity.distance_m, original_distance_m)

    def test_reconcile_does_not_modify_assignment(self):
        original_status = self.assignment.status
        reconcile(assignment=self.assignment, activity=self.activity)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, original_status)

    def test_planned_workout_has_no_actual_fields(self):
        """PlannedWorkout must not gain execution-side fields (structural guard)."""
        planned_field_names = {f.name for f in PlannedWorkout._meta.get_fields()}
        execution_field_names = {"actual_duration", "actual_distance", "actual_hr", "completion_time"}
        overlap = planned_field_names & execution_field_names
        self.assertEqual(overlap, set(), f"PlannedWorkout has execution fields: {overlap}")


# ==============================================================================
# Score Engine Tests
# ==============================================================================

class ScoreEngineTests(TestCase):

    def setUp(self):
        self.coach_user = _make_user("score_coach")
        self.org        = _make_org("ScoreOrg")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)
        self.athlete_user = _make_user("score_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete  = _make_athlete(self.athlete_user, self.org)
        self.alumno   = _make_alumno(self.athlete_user, self.coach_user)
        self.library  = _make_library(self.org)
        self.workout  = _make_planned_workout(
            self.org, self.library,
            estimated_duration_seconds=3600,   # 60 min
            estimated_distance_meters=10000,   # 10 km
        )
        self.assignment = _make_assignment(self.org, self.athlete, self.workout)

    def _activity(self, duration_s=3600, distance_m=10000.0, sport="RUN",
                  start_time=None):
        return _make_activity(
            self.coach_user, self.alumno, self.athlete,
            sport=sport, duration_s=duration_s,
            distance_m=distance_m, start_time=start_time,
        )

    # 1. Perfect match — score 100

    def test_perfect_match_score_100(self):
        activity = self._activity(duration_s=3600, distance_m=10000.0)
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.category, "completed")

    # 2. Under-compliance

    def test_under_compliance_50_percent_duration(self):
        activity = self._activity(duration_s=1800, distance_m=5000.0)  # 50%
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 50)
        self.assertEqual(result.category, "not_completed")
        self.assertIn(ComplianceSignal.UNDER_COMPLETED, result.signals)
        self.assertIn(ComplianceSignal.DURATION_SHORT, result.signals)

    def test_under_compliance_75_percent_is_regular(self):
        activity = self._activity(duration_s=2700, distance_m=7500.0)  # 75%
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 75)
        self.assertEqual(result.category, "regular")

    # 3. Over-compliance capped at 120

    def test_over_compliance_150_percent_capped_at_120(self):
        activity = self._activity(duration_s=5400, distance_m=15000.0)  # 150%
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 120)
        self.assertEqual(result.category, "over_completed")
        self.assertIn(ComplianceSignal.OVER_COMPLETED, result.signals)

    def test_over_compliance_110_percent_score_110(self):
        activity = self._activity(duration_s=3960, distance_m=11000.0)  # 110%
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 110)
        self.assertEqual(result.category, "over_completed")

    # 4. Higher-intensity pace signal

    def test_faster_pace_generates_pace_signal(self):
        # Planned: 3600s / 10km = 360s/km. Actual: 3000s / 10km = 300s/km (faster)
        activity = self._activity(duration_s=3000, distance_m=10000.0)
        result   = score_compliance(self.assignment, activity)
        self.assertIn(ComplianceSignal.PACE_OUT_OF_TARGET, result.signals)

    def test_slower_pace_generates_pace_signal(self):
        # Planned: 360s/km. Actual: 3600s / 7000m = 514s/km (much slower)
        activity = self._activity(duration_s=3600, distance_m=7000.0)
        result   = score_compliance(self.assignment, activity)
        self.assertIn(ComplianceSignal.PACE_OUT_OF_TARGET, result.signals)

    # 10. Score clamped at 0

    def test_score_clamped_at_zero_no_actual_data(self):
        activity = self._activity(duration_s=0, distance_m=0.0)
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, SCORE_MIN)
        self.assertGreaterEqual(result.score, 0)

    # 11. Score clamped at 120

    def test_score_clamped_at_max_enormous_overrun(self):
        activity = self._activity(duration_s=36000, distance_m=100000.0)  # 1000%
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, SCORE_MAX)
        self.assertLessEqual(result.score, 120)

    # 12. Compliance category boundary coverage

    def test_compliance_range_not_completed(self):
        activity = self._activity(duration_s=1800)   # 50% → score 50
        result = score_compliance(self.assignment, activity)
        self.assertEqual(result.category, "not_completed")

    def test_compliance_range_regular(self):
        activity = self._activity(duration_s=2520)   # 70% → score 70
        result = score_compliance(self.assignment, activity)
        self.assertEqual(result.category, "regular")

    def test_compliance_range_completed(self):
        result = score_compliance(
            self.assignment,
            self._activity(duration_s=3600),   # 100% → score 100
        )
        self.assertEqual(result.category, "completed")

    def test_compliance_range_over_completed(self):
        result = score_compliance(
            self.assignment,
            self._activity(duration_s=3780),   # 105% → score 105
        )
        self.assertEqual(result.category, "over_completed")

    def test_all_compliance_ranges_covered(self):
        """COMPLIANCE_RANGES must cover 0..120 without gap or overlap."""
        covered = set()
        for lo, hi, _ in COMPLIANCE_RANGES:
            for s in range(lo, hi + 1):
                self.assertNotIn(s, covered, f"Score {s} covered twice in COMPLIANCE_RANGES")
                covered.add(s)
        self.assertEqual(min(covered), 0)
        self.assertEqual(max(covered), 120)

    # 15. Explicit primary_target_variable override

    def test_primary_target_variable_distance_drives_score(self):
        # Planned duration=3600, distance=10000. Actual duration=1000 (short),
        # distance=10000 (exact). Primary target = distance → score should be 100.
        self.workout.primary_target_variable = "distance"
        self.workout.save()
        activity = self._activity(duration_s=1000, distance_m=10000.0)
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.primary_target, "distance")

    def test_primary_target_variable_duration_drives_score(self):
        self.workout.primary_target_variable = "duration"
        self.workout.save()
        activity = self._activity(duration_s=3600, distance_m=5000.0)  # distance short
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(result.score, 100)          # duration exact
        self.assertEqual(result.primary_target, "duration")

    # Possible overreaching signal

    def test_possible_overreaching_signal(self):
        # Duration 130%, distance 130%, score > 110 → POSSIBLE_OVERREACHING
        activity = self._activity(
            duration_s=int(3600 * 1.3),
            distance_m=10000 * 1.3,
        )
        result = score_compliance(self.assignment, activity)
        self.assertIn(ComplianceSignal.POSSIBLE_OVERREACHING, result.signals)

    # Signals deduplication

    def test_signals_deduplicated(self):
        activity = self._activity(duration_s=1800, distance_m=5000.0)
        result   = score_compliance(self.assignment, activity)
        self.assertEqual(len(result.signals), len(set(result.signals)))


# ==============================================================================
# Matching Tests
# ==============================================================================

class MatchingTests(TestCase):

    def setUp(self):
        self.coach_user   = _make_user("match_coach")
        self.org          = _make_org("MatchOrg")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)
        self.athlete_user = _make_user("match_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete  = _make_athlete(self.athlete_user, self.org)
        self.alumno   = _make_alumno(self.athlete_user, self.coach_user)
        self.library  = _make_library(self.org)
        self.workout  = _make_planned_workout(
            self.org, self.library,
            estimated_duration_seconds=3600,
            estimated_distance_meters=10000,
        )
        self.assignment = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 4, 1),
        )

    def _activity_on(self, date, sport="RUN", suffix=""):
        start = timezone.make_aware(datetime.datetime(date.year, date.month, date.day, 8, 0))
        return _make_activity(
            self.coach_user, self.alumno, self.athlete,
            sport=sport, duration_s=3600, distance_m=10000.0,
            start_time=start,
        )

    # 6. No activity in window → UNMATCHED

    def test_no_activity_in_window_returns_no_match(self):
        activity, confidence, reason = find_best_match(self.assignment, window_days=1)
        self.assertIsNone(activity)
        self.assertIsNotNone(reason)

    # 7. Ambiguous match (two activities on same day)

    def test_ambiguous_match_two_candidates_fail_closed(self):
        # Two activities on the same day, same discipline
        self._activity_on(datetime.date(2026, 4, 1))
        # Second activity needs different provider_activity_id — use start_time variation
        start2 = timezone.make_aware(datetime.datetime(2026, 4, 1, 14, 0))
        _make_activity(
            self.coach_user, self.alumno, self.athlete,
            sport="RUN", duration_s=1800, distance_m=5000.0,
            start_time=start2,
        )
        activity, confidence, reason = find_best_match(self.assignment)
        self.assertIsNone(activity)
        self.assertEqual(reason, "ambiguous")
        self.assertAlmostEqual(confidence, 0.0)

    # 8. Organization isolation: cross-org activity not matched

    def test_cross_org_activity_not_matched(self):
        org_b       = _make_org("MatchOrgB")
        coach_b     = _make_user("match_coach_b")
        _make_membership(coach_b, org_b, "coach")
        athlete_b_user = _make_user("match_athlete_b")
        _make_membership(athlete_b_user, org_b, "athlete")
        athlete_b   = _make_athlete(athlete_b_user, org_b)
        alumno_b    = _make_alumno(athlete_b_user, coach_b)

        # Activity belongs to athlete_b (different org) on the same date
        _make_activity(
            coach_b, alumno_b, athlete_b,
            sport="RUN", duration_s=3600, distance_m=10000.0,
            start_time=timezone.make_aware(datetime.datetime(2026, 4, 1, 8, 0)),
        )

        activity, confidence, reason = find_best_match(self.assignment)
        self.assertIsNone(activity)

    # Matching finds correct single candidate

    def test_exact_match_returns_activity_confidence_1(self):
        activity = self._activity_on(datetime.date(2026, 4, 1))
        matched, confidence, reason = find_best_match(self.assignment)
        self.assertEqual(matched, activity)
        self.assertAlmostEqual(confidence, 1.0)
        self.assertIsNone(reason)

    def test_off_by_one_day_returns_lower_confidence(self):
        activity = self._activity_on(datetime.date(2026, 4, 2))  # ±1 day
        matched, confidence, reason = find_best_match(self.assignment)
        self.assertEqual(matched, activity)
        self.assertLess(confidence, 1.0)
        self.assertGreaterEqual(confidence, AUTO_MATCH_CONFIDENCE_THRESHOLD)

    # 17. No athlete FK on assignment → skip gracefully
    # WorkoutAssignment enforces non-null athlete at both the model and DB level.
    # We simulate a legacy assignment (pre-PR-114 backfill) by constructing a
    # minimal in-memory stub that has athlete=None, exercising the service's
    # early-return guard without a DB round-trip.

    def test_no_athlete_fk_on_assignment_skips_match(self):
        from types import SimpleNamespace
        stub = SimpleNamespace(
            athlete=None,
            pk=self.assignment.pk,
            organization_id=self.assignment.organization_id,
        )
        # Create an activity — it must NOT be matched to this stub
        self._activity_on(datetime.date(2026, 4, 1))
        matched, confidence, reason = find_best_match(stub)
        self.assertIsNone(matched)
        self.assertEqual(reason, "no_athlete_fk_on_assignment")

    # Already-reconciled activity excluded from future matches

    def test_already_reconciled_activity_excluded(self):
        activity = self._activity_on(datetime.date(2026, 4, 1))
        # Reconcile it to this assignment
        reconcile(assignment=self.assignment, activity=activity)
        # A different assignment for the same athlete on the same day
        assignment2 = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 4, 1),
            day_order=2,
        )
        matched, _, _ = find_best_match(assignment2)
        self.assertIsNone(matched)


# ==============================================================================
# Reconciliation Operation Tests
# ==============================================================================

class ReconciliationOperationTests(TestCase):

    def setUp(self):
        self.coach_user   = _make_user("rec_coach")
        self.org          = _make_org("RecOrg")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)
        self.athlete_user = _make_user("rec_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete  = _make_athlete(self.athlete_user, self.org)
        self.alumno   = _make_alumno(self.athlete_user, self.coach_user)
        self.library  = _make_library(self.org)
        self.workout  = _make_planned_workout(
            self.org, self.library,
            estimated_duration_seconds=3600,
            estimated_distance_meters=10000,
        )
        self.assignment = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 4, 1),
        )
        self.activity = _make_activity(
            self.coach_user, self.alumno, self.athlete,
            duration_s=3600, distance_m=10000.0,
        )

    # 5. No activity → MISSED

    def test_mark_missed_state(self):
        rec = mark_assignment_missed(assignment=self.assignment)
        self.assertEqual(rec.state, WorkoutReconciliation.State.MISSED)
        self.assertEqual(rec.compliance_score, 0)
        self.assertEqual(rec.compliance_category, "not_completed")
        self.assertIn(ComplianceSignal.PLANNED_BUT_NOT_EXECUTED, rec.signals)
        self.assertIsNone(rec.completed_activity)

    # 13. Idempotent reconcile

    def test_reconcile_is_idempotent(self):
        reconcile(assignment=self.assignment, activity=self.activity)
        reconcile(assignment=self.assignment, activity=self.activity)
        count = WorkoutReconciliation.objects.filter(assignment=self.assignment).count()
        self.assertEqual(count, 1)

    def test_reconcile_then_mark_missed_updates_in_place(self):
        reconcile(assignment=self.assignment, activity=self.activity)
        mark_assignment_missed(assignment=self.assignment)
        count = WorkoutReconciliation.objects.filter(assignment=self.assignment).count()
        self.assertEqual(count, 1)
        rec = WorkoutReconciliation.objects.get(assignment=self.assignment)
        self.assertEqual(rec.state, WorkoutReconciliation.State.MISSED)

    # Organization derived from assignment

    def test_reconcile_organization_derived_from_assignment(self):
        rec = reconcile(assignment=self.assignment, activity=self.activity)
        self.assertEqual(rec.organization_id, self.org.id)

    # reconciled_at is set on reconcile

    def test_reconcile_sets_reconciled_at(self):
        rec = reconcile(assignment=self.assignment, activity=self.activity)
        self.assertIsNotNone(rec.reconciled_at)

    # State after perfect reconcile

    def test_reconcile_with_activity_sets_reconciled_state(self):
        rec = reconcile(assignment=self.assignment, activity=self.activity)
        self.assertEqual(rec.state, WorkoutReconciliation.State.RECONCILED)
        self.assertIsNotNone(rec.compliance_score)
        self.assertIsNotNone(rec.compliance_category)

    # score_detail has expected structure

    def test_score_detail_has_duration_key(self):
        rec = reconcile(assignment=self.assignment, activity=self.activity)
        self.assertIn("duration", rec.score_detail)
        self.assertIn("actual", rec.score_detail["duration"])
        self.assertIn("planned", rec.score_detail["duration"])
        self.assertIn("score", rec.score_detail["duration"])

    # 16. auto_match_and_reconcile creates RECONCILED record

    def test_auto_match_and_reconcile_creates_reconciled_record(self):
        rec = auto_match_and_reconcile(assignment=self.assignment)
        self.assertEqual(rec.state, WorkoutReconciliation.State.RECONCILED)
        self.assertEqual(rec.match_method, WorkoutReconciliation.MatchMethod.AUTO)
        self.assertIsNotNone(rec.match_confidence)
        self.assertEqual(rec.compliance_score, 100)

    def test_auto_match_no_activity_creates_unmatched_record(self):
        # No activity exists → UNMATCHED
        self.activity.delete()
        rec = auto_match_and_reconcile(assignment=self.assignment)
        self.assertEqual(rec.state, WorkoutReconciliation.State.UNMATCHED)

    def test_auto_match_ambiguous_creates_ambiguous_record(self):
        # Create a second activity on the same day/discipline
        start2 = timezone.make_aware(datetime.datetime(2026, 4, 1, 14, 0))
        _make_activity(
            self.coach_user, self.alumno, self.athlete,
            sport="RUN", duration_s=1800, distance_m=5000.0,
            start_time=start2,
        )
        rec = auto_match_and_reconcile(assignment=self.assignment)
        self.assertEqual(rec.state, WorkoutReconciliation.State.AMBIGUOUS)
        self.assertIsNone(rec.compliance_score)


# ==============================================================================
# Weekly Adherence Tests
# ==============================================================================

class WeeklyAdherenceTests(TestCase):

    def setUp(self):
        self.coach_user   = _make_user("week_coach")
        self.org          = _make_org("WeekOrg")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)
        self.athlete_user = _make_user("week_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete  = _make_athlete(self.athlete_user, self.org)
        self.alumno   = _make_alumno(self.athlete_user, self.coach_user)
        self.library  = _make_library(self.org)
        self.week_start = datetime.date(2026, 4, 6)   # Monday

        # Create 3 assignments spread across the week
        self.workouts = []
        self.assignments = []
        for i in range(3):
            w = _make_planned_workout(
                self.org, self.library,
                name=f"Workout {i}",
                estimated_duration_seconds=3600,
                estimated_distance_meters=10000,
            )
            a = _make_assignment(
                self.org, self.athlete, w,
                scheduled_date=self.week_start + datetime.timedelta(days=i),
                day_order=1,
            )
            self.workouts.append(w)
            self.assignments.append(a)

        # Create an activity for the first assignment (reconciled)
        start1 = timezone.make_aware(
            datetime.datetime(2026, 4, 6, 8, 0)
        )
        self.activity1 = _make_activity(
            self.coach_user, self.alumno, self.athlete,
            duration_s=3600, distance_m=10000.0,
            start_time=start1,
        )

    # 9. Weekly adherence correctness

    def test_weekly_adherence_counts(self):
        # Reconcile assignment 0, miss assignment 1, leave assignment 2 unmatched
        reconcile(assignment=self.assignments[0], activity=self.activity1)
        mark_assignment_missed(assignment=self.assignments[1])
        auto_match_and_reconcile(assignment=self.assignments[2])  # no activity → unmatched

        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=self.week_start,
        )
        self.assertEqual(result.planned_count, 3)
        self.assertEqual(result.reconciled_count, 1)
        self.assertEqual(result.missed_count, 1)
        self.assertEqual(result.unmatched_count, 1)

    def test_weekly_adherence_pct_one_of_three(self):
        reconcile(assignment=self.assignments[0], activity=self.activity1)
        mark_assignment_missed(assignment=self.assignments[1])
        auto_match_and_reconcile(assignment=self.assignments[2])

        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=self.week_start,
        )
        self.assertAlmostEqual(result.adherence_pct, 100 / 3, places=1)

    def test_weekly_adherence_zero_planned(self):
        # Empty week — no assignments
        future_week = datetime.date(2030, 1, 1)
        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=future_week,
        )
        self.assertEqual(result.planned_count, 0)
        self.assertEqual(result.adherence_pct, 0.0)

    def test_weekly_adherence_perfect_all_reconciled(self):
        for i, assignment in enumerate(self.assignments):
            start = timezone.make_aware(
                datetime.datetime(2026, 4, 6 + i, 8, 0)
            )
            activity = _make_activity(
                self.coach_user, self.alumno, self.athlete,
                sport="RUN", duration_s=3600, distance_m=10000.0,
                start_time=start,
            )
            reconcile(assignment=assignment, activity=activity)

        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=self.week_start,
        )
        self.assertEqual(result.reconciled_count, 3)
        self.assertAlmostEqual(result.adherence_pct, 100.0)
        self.assertEqual(result.avg_compliance_score, 100.0)

    def test_weekly_adherence_avg_score_excludes_null_scores(self):
        # Reconcile one, leave others ambiguous (null score)
        reconcile(assignment=self.assignments[0], activity=self.activity1)
        # Leave assignments[1] and [2] unmatched (null score)
        auto_match_and_reconcile(assignment=self.assignments[1])
        auto_match_and_reconcile(assignment=self.assignments[2])

        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=self.week_start,
        )
        # avg_score should only include score from assignments[0]
        self.assertEqual(result.avg_compliance_score, 100.0)

    def test_weekly_adherence_org_isolation(self):
        """Activity from another org's athlete must not appear in this org's adherence."""
        org_b    = _make_org("WeekOrgB")
        coach_b  = _make_user("week_coach_b")
        _make_membership(coach_b, org_b, "coach")
        _make_coach(coach_b, org_b)
        athlete_b_user = _make_user("week_athlete_b")
        _make_membership(athlete_b_user, org_b, "athlete")
        athlete_b   = _make_athlete(athlete_b_user, org_b)
        alumno_b    = _make_alumno(athlete_b_user, coach_b)
        library_b   = _make_library(org_b, "Lib B")
        workout_b   = _make_planned_workout(org_b, library_b, name="W B",
                                            estimated_duration_seconds=3600)
        assignment_b = _make_assignment(
            org_b, athlete_b, workout_b,
            scheduled_date=self.week_start,
        )
        activity_b = _make_activity(
            coach_b, alumno_b, athlete_b,
            start_time=timezone.make_aware(datetime.datetime(2026, 4, 6, 8, 0)),
        )
        reconcile(assignment=assignment_b, activity=activity_b)

        result = compute_weekly_adherence(
            organization=self.org,
            athlete=self.athlete,
            week_start=self.week_start,
        )
        # Org A has no reconciliations yet → planned=0 (no reconciliation records)
        self.assertEqual(result.planned_count, 0)
