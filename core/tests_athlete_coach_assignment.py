"""
core/tests_athlete_coach_assignment.py

Tests for AthleteCoachAssignment model and services (PR-104).

Covers:
- Model creation and field defaults
- UniqueConstraint: one active primary coach per (athlete, org)
- Multiple assistant coaches allowed
- Ended assignment allows new primary
- Cross-organization assignment denied at service layer
- History preservation (ended records not deleted)
- Cascade behavior
- is_active property
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Athlete, AthleteCoachAssignment, Coach, Organization, Team
from .services_assignment import assign_coach_to_athlete, end_coach_assignment

User = get_user_model()


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


class AthleteCoachAssignmentModelTests(TestCase):
    def setUp(self):
        self.org = _org("model-org")
        self.coach = _coach(_user("c1"), self.org)
        self.athlete = _athlete(_user("a1"), self.org)

    def test_assignment_created_with_required_fields(self):
        a = AthleteCoachAssignment.objects.create(
            athlete=self.athlete,
            coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.assertEqual(a.athlete, self.athlete)
        self.assertEqual(a.coach, self.coach)
        self.assertEqual(a.organization, self.org)
        self.assertEqual(a.role, AthleteCoachAssignment.Role.PRIMARY)
        self.assertIsNone(a.ended_at)
        self.assertIsNotNone(a.assigned_at)

    def test_is_active_property_true_when_ended_at_none(self):
        a = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.assertTrue(a.is_active)

    def test_is_active_property_false_when_ended_at_set(self):
        from django.utils import timezone
        a = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
            ended_at=timezone.now(),
        )
        self.assertFalse(a.is_active)

    def test_primary_constraint_prevents_two_active_primary_assignments(self):
        AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        coach2 = _coach(_user("c2"), self.org)
        with self.assertRaises(IntegrityError):
            AthleteCoachAssignment.objects.create(
                athlete=self.athlete, coach=coach2,
                organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
            )

    def test_multiple_assistant_coaches_allowed(self):
        coach2 = _coach(_user("ca2"), self.org)
        coach3 = _coach(_user("ca3"), self.org)
        a1 = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=coach2,
            organization=self.org, role=AthleteCoachAssignment.Role.ASSISTANT,
        )
        a2 = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=coach3,
            organization=self.org, role=AthleteCoachAssignment.Role.ASSISTANT,
        )
        self.assertEqual(a1.role, AthleteCoachAssignment.Role.ASSISTANT)
        self.assertEqual(a2.role, AthleteCoachAssignment.Role.ASSISTANT)

    def test_ended_primary_allows_new_primary(self):
        from django.utils import timezone
        # Create and end first primary assignment
        first = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
            ended_at=timezone.now(),
        )
        self.assertFalse(first.is_active)
        # New primary can now be created
        coach2 = _coach(_user("c_new"), self.org)
        second = AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=coach2,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.assertTrue(second.is_active)

    def test_assignment_str(self):
        a = AthleteCoachAssignment(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        result = str(a)
        self.assertIn("primary", result)
        self.assertIn("active", result)

    def test_cascade_delete_with_athlete(self):
        AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.assertEqual(AthleteCoachAssignment.objects.count(), 1)
        self.athlete.delete()
        self.assertEqual(AthleteCoachAssignment.objects.count(), 0)

    def test_cascade_delete_with_coach(self):
        AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.coach.delete()
        self.assertEqual(AthleteCoachAssignment.objects.count(), 0)

    def test_cascade_delete_with_organization(self):
        AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach,
            organization=self.org, role=AthleteCoachAssignment.Role.PRIMARY,
        )
        self.org.delete()
        self.assertEqual(AthleteCoachAssignment.objects.count(), 0)


class AssignmentServiceTests(TestCase):
    def setUp(self):
        self.org = _org("svc-org")
        self.coach_user = _user("svc_coach")
        self.athlete_user = _user("svc_athlete")
        self.coach = _coach(self.coach_user, self.org)
        self.athlete = _athlete(self.athlete_user, self.org)

    def test_assign_coach_to_athlete_success(self):
        assignment = assign_coach_to_athlete(
            athlete=self.athlete,
            coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        self.assertEqual(assignment.athlete, self.athlete)
        self.assertEqual(assignment.coach, self.coach)
        self.assertEqual(assignment.role, AthleteCoachAssignment.Role.PRIMARY)
        self.assertTrue(assignment.is_active)

    def test_assign_raises_if_athlete_wrong_org(self):
        other_org = _org("other-org-a")
        other_athlete = _athlete(_user("oa"), other_org)
        with self.assertRaises(ValidationError):
            assign_coach_to_athlete(
                athlete=other_athlete,
                coach=self.coach,
                organization=self.org,
                role=AthleteCoachAssignment.Role.PRIMARY,
                assigned_by=self.coach_user,
            )

    def test_assign_raises_if_coach_wrong_org(self):
        other_org = _org("other-org-c")
        other_coach = _coach(_user("oc"), other_org)
        with self.assertRaises(ValidationError):
            assign_coach_to_athlete(
                athlete=self.athlete,
                coach=other_coach,
                organization=self.org,
                role=AthleteCoachAssignment.Role.PRIMARY,
                assigned_by=self.coach_user,
            )

    def test_assign_raises_on_duplicate_primary(self):
        assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        coach2 = _coach(_user("coach2"), self.org)
        with self.assertRaises(ValidationError):
            assign_coach_to_athlete(
                athlete=self.athlete, coach=coach2,
                organization=self.org,
                role=AthleteCoachAssignment.Role.PRIMARY,
                assigned_by=self.coach_user,
            )

    def test_assign_assistant_does_not_conflict_with_primary(self):
        assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        asst_coach = _coach(_user("asst"), self.org)
        asst = assign_coach_to_athlete(
            athlete=self.athlete, coach=asst_coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.ASSISTANT,
            assigned_by=self.coach_user,
        )
        self.assertEqual(asst.role, AthleteCoachAssignment.Role.ASSISTANT)

    def test_end_assignment_sets_ended_at(self):
        assignment = assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        self.assertTrue(assignment.is_active)
        ended = end_coach_assignment(assignment)
        self.assertIsNotNone(ended.ended_at)
        self.assertFalse(ended.is_active)

    def test_end_already_ended_assignment_raises(self):
        assignment = assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        end_coach_assignment(assignment)
        with self.assertRaises(ValidationError):
            end_coach_assignment(assignment)

    def test_assignment_history_preserved_on_end(self):
        assignment = assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        end_coach_assignment(assignment)
        # Record still exists in DB
        self.assertEqual(
            AthleteCoachAssignment.objects.filter(id=assignment.id).count(), 1
        )
        assignment.refresh_from_db()
        self.assertIsNotNone(assignment.ended_at)

    def test_new_primary_allowed_after_ending_previous(self):
        first = assign_coach_to_athlete(
            athlete=self.athlete, coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        end_coach_assignment(first)
        coach2 = _coach(_user("coach_next"), self.org)
        second = assign_coach_to_athlete(
            athlete=self.athlete, coach=coach2,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
            assigned_by=self.coach_user,
        )
        self.assertTrue(second.is_active)
        # Both records exist — history preserved
        self.assertEqual(
            AthleteCoachAssignment.objects.filter(athlete=self.athlete).count(), 2
        )
