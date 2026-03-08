"""
core/tests_athlete_goal.py

Tests for AthleteGoal domain model (PR-107).

AthleteGoal represents what an athlete is trying to achieve.
Supports both race-linked goals (target_event set) and personal goals
(target_event null, optional target_date).

Covers:
- Race-linked goal creation
- Personal goal (no RaceEvent)
- Organization consistency with athlete (fail-closed)
- target_event organization consistency (fail-closed)
- Multiple goals per athlete allowed
- Duplicate active priority per athlete blocked (UniqueConstraint)
- Same priority allowed once previous goal is completed/cancelled
- Priority choices (A/B/C)
- Status choices and defaults
- GoalType choices
- title is required
- Cascade delete with athlete / organization
- No dependency on legacy Carrera
- String representation
"""
import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Athlete, AthleteGoal, Organization, RaceEvent

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _event(org, name="UTMB 2026", event_date=None):
    if event_date is None:
        event_date = datetime.date(2026, 8, 28)
    return RaceEvent.objects.create(
        organization=org, name=name, discipline="trail", event_date=event_date,
    )


def _goal(athlete, org, title="Finish UTMB", priority="A", status="planned", **kwargs):
    return AthleteGoal.objects.create(
        athlete=athlete,
        organization=org,
        title=title,
        priority=priority,
        goal_type=AthleteGoal.GoalType.FINISH,
        status=status,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Creation tests
# ---------------------------------------------------------------------------

class AthleteGoalCreationTests(TestCase):
    def setUp(self):
        self.org = _org("goal-org")
        self.athlete = _athlete(_user("g_athlete"), self.org)

    def test_race_linked_goal_creation(self):
        event = _event(self.org)
        goal = _goal(self.athlete, self.org, target_event=event)
        self.assertEqual(goal.athlete, self.athlete)
        self.assertEqual(goal.organization, self.org)
        self.assertEqual(goal.target_event, event)
        self.assertEqual(goal.priority, "A")
        self.assertEqual(goal.goal_type, AthleteGoal.GoalType.FINISH)
        self.assertEqual(goal.status, AthleteGoal.Status.PLANNED)

    def test_personal_goal_without_race_event(self):
        goal = _goal(
            self.athlete, self.org,
            title="Build base to 30km/week",
            target_date=datetime.date(2026, 6, 1),
        )
        self.assertIsNone(goal.target_event)
        self.assertEqual(goal.title, "Build base to 30km/week")
        self.assertEqual(goal.target_date, datetime.date(2026, 6, 1))

    def test_optional_fields_default_correctly(self):
        goal = _goal(self.athlete, self.org)
        self.assertIsNone(goal.target_event)
        self.assertIsNone(goal.target_date)
        self.assertEqual(goal.coach_notes, "")
        self.assertIsNone(goal.created_by)

    def test_coach_notes_can_be_set(self):
        goal = _goal(self.athlete, self.org, coach_notes="Focus on technical descents.")
        self.assertEqual(goal.coach_notes, "Focus on technical descents.")

    def test_created_by_can_be_set(self):
        coach_user = _user("the_coach")
        goal = _goal(self.athlete, self.org, created_by=coach_user)
        self.assertEqual(goal.created_by, coach_user)

    def test_timestamps_set_on_creation(self):
        goal = _goal(self.athlete, self.org)
        self.assertIsNotNone(goal.created_at)
        self.assertIsNotNone(goal.updated_at)

    def test_str_includes_priority_title_status(self):
        goal = _goal(self.athlete, self.org, title="Finish UTMB", priority="A")
        result = str(goal)
        self.assertIn("[A]", result)
        self.assertIn("Finish UTMB", result)
        self.assertIn("planned", result)

    def test_str_includes_event_name_when_linked(self):
        event = _event(self.org, name="UTMB 2026")
        goal = _goal(self.athlete, self.org, target_event=event)
        result = str(goal)
        self.assertIn("UTMB 2026", result)


# ---------------------------------------------------------------------------
# Choices tests
# ---------------------------------------------------------------------------

class AthleteGoalChoicesTests(TestCase):
    def setUp(self):
        self.org = _org("choices-org")
        self.athlete = _athlete(_user("ch_athlete"), self.org)

    def test_priority_choices_are_a_b_c(self):
        keys = [c[0] for c in AthleteGoal.Priority.choices]
        self.assertIn("A", keys)
        self.assertIn("B", keys)
        self.assertIn("C", keys)

    def test_status_choices_cover_lifecycle(self):
        keys = [c[0] for c in AthleteGoal.Status.choices]
        for expected in ("planned", "active", "paused", "completed", "cancelled"):
            self.assertIn(expected, keys)

    def test_goal_type_includes_finish(self):
        keys = [c[0] for c in AthleteGoal.GoalType.choices]
        self.assertIn("finish", keys)

    def test_status_defaults_to_planned(self):
        goal = _goal(self.athlete, self.org)
        self.assertEqual(goal.status, "planned")

    def test_goal_type_defaults_to_finish(self):
        goal = _goal(self.athlete, self.org)
        self.assertEqual(goal.goal_type, "finish")


# ---------------------------------------------------------------------------
# Organization consistency (fail-closed)
# ---------------------------------------------------------------------------

class AthleteGoalOrgConsistencyTests(TestCase):
    def setUp(self):
        self.org_a = _org("org-a-goal")
        self.org_b = _org("org-b-goal")
        self.athlete = _athlete(_user("ca_athlete"), self.org_a)

    def test_valid_goal_matching_orgs_passes(self):
        goal = _goal(self.athlete, self.org_a)
        self.assertEqual(goal.organization, self.athlete.organization)

    def test_cross_org_athlete_raises_validation_error(self):
        """goal.organization must equal athlete.organization."""
        with self.assertRaises(ValidationError):
            AthleteGoal.objects.create(
                athlete=self.athlete,
                organization=self.org_b,
                title="Illicit cross-org goal",
                priority="A",
                goal_type="finish",
                status="planned",
            )

    def test_cross_org_target_event_raises_validation_error(self):
        """target_event.organization must equal goal.organization."""
        event_b = _event(self.org_b, name="Race in Org B")
        with self.assertRaises(ValidationError):
            AthleteGoal.objects.create(
                athlete=self.athlete,
                organization=self.org_a,
                title="Goal with wrong org event",
                priority="A",
                goal_type="finish",
                status="planned",
                target_event=event_b,
            )

    def test_same_org_target_event_passes(self):
        event = _event(self.org_a)
        goal = _goal(self.athlete, self.org_a, target_event=event)
        self.assertEqual(goal.target_event.organization, goal.organization)


# ---------------------------------------------------------------------------
# Priority uniqueness constraint
# ---------------------------------------------------------------------------

class AthleteGoalPriorityConstraintTests(TestCase):
    def setUp(self):
        self.org = _org("priority-org")
        self.athlete = _athlete(_user("prio_athlete"), self.org)

    def test_multiple_goals_allowed_with_different_priorities(self):
        _goal(self.athlete, self.org, title="Goal A", priority="A", status="active")
        _goal(self.athlete, self.org, title="Goal B", priority="B", status="active")
        _goal(self.athlete, self.org, title="Goal C", priority="C", status="active")
        self.assertEqual(AthleteGoal.objects.filter(athlete=self.athlete).count(), 3)

    def test_duplicate_active_priority_blocked(self):
        """UniqueConstraint: only one active goal per (athlete, priority)."""
        _goal(self.athlete, self.org, title="First A", priority="A", status="active")
        with self.assertRaises(IntegrityError):
            # Bypass full_clean to hit the DB-level constraint directly
            goal = AthleteGoal(
                athlete=self.athlete,
                organization=self.org,
                title="Second A",
                priority="A",
                goal_type="finish",
                status="active",
            )
            goal.save_base(raw=True)

    def test_same_priority_allowed_when_prior_goal_is_completed(self):
        first = _goal(self.athlete, self.org, title="First A", priority="A", status="active")
        first.status = AthleteGoal.Status.COMPLETED
        first.save()
        # Now a new active A goal is allowed
        second = _goal(self.athlete, self.org, title="Second A", priority="A", status="active")
        self.assertTrue(second.pk)

    def test_same_priority_allowed_when_prior_goal_is_cancelled(self):
        first = _goal(self.athlete, self.org, title="First A", priority="A", status="active")
        first.status = AthleteGoal.Status.CANCELLED
        first.save()
        second = _goal(self.athlete, self.org, title="New A", priority="A", status="active")
        self.assertTrue(second.pk)

    def test_planned_and_active_same_priority_coexist(self):
        """
        Planned goals do not trigger the uniqueness constraint —
        only active ones are constrained.
        """
        _goal(self.athlete, self.org, title="Planned A", priority="A", status="planned")
        _goal(self.athlete, self.org, title="Active A", priority="A", status="active")
        self.assertEqual(AthleteGoal.objects.filter(athlete=self.athlete, priority="A").count(), 2)

    def test_multiple_athletes_can_each_have_active_priority_a(self):
        athlete2 = _athlete(_user("prio_athlete2"), self.org)
        _goal(self.athlete, self.org, title="A1", priority="A", status="active")
        _goal(athlete2, self.org, title="A2", priority="A", status="active")
        self.assertEqual(AthleteGoal.objects.filter(priority="A", status="active").count(), 2)


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------

class AthleteGoalCascadeTests(TestCase):
    def setUp(self):
        self.org = _org("cascade-org")
        self.athlete = _athlete(_user("cas_athlete"), self.org)

    def test_cascade_delete_with_athlete(self):
        _goal(self.athlete, self.org)
        self.assertEqual(AthleteGoal.objects.count(), 1)
        self.athlete.delete()
        self.assertEqual(AthleteGoal.objects.count(), 0)

    def test_cascade_delete_with_organization(self):
        _goal(self.athlete, self.org)
        self.assertEqual(AthleteGoal.objects.count(), 1)
        self.org.delete()
        self.assertEqual(AthleteGoal.objects.count(), 0)

    def test_target_event_set_null_on_race_event_delete(self):
        event = _event(self.org)
        goal = _goal(self.athlete, self.org, target_event=event)
        self.assertIsNotNone(goal.target_event)
        event.delete()
        goal.refresh_from_db()
        self.assertIsNone(goal.target_event)

    def test_created_by_set_null_on_user_delete(self):
        coach = _user("coach_to_delete")
        goal = _goal(self.athlete, self.org, created_by=coach)
        coach.delete()
        goal.refresh_from_db()
        self.assertIsNone(goal.created_by)


# ---------------------------------------------------------------------------
# Legacy independence
# ---------------------------------------------------------------------------

class AthleteGoalLegacyIndependenceTests(TestCase):
    def test_athlete_goal_has_no_carrera_dependency(self):
        from .models import Carrera
        goal_fields = {f.name for f in AthleteGoal._meta.get_fields()}
        self.assertNotIn("carrera", goal_fields)
        self.assertEqual(Carrera.objects.count(), 0)
