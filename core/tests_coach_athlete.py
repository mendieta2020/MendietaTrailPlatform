"""
core/tests_coach_athlete.py

Tests for Coach and Athlete domain models (PR-103).

These are organization-scoped identity models that form the P1 domain
foundation. No existing model (Alumno, Entrenamiento, Actividad) is
modified by this PR. The legacy coexistence test verifies this explicitly.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .models import Alumno, Athlete, Coach, Membership, Organization, Team

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


class CoachModelTests(TestCase):
    def setUp(self):
        self.user = _make_user("coach_user")
        self.org = _make_org("coach-org")

    def test_coach_requires_organization(self):
        coach = Coach.objects.create(user=self.user, organization=self.org)
        self.assertEqual(coach.organization, self.org)
        self.assertEqual(coach.user, self.user)

    def test_coach_is_active_defaults_to_true(self):
        coach = Coach.objects.create(user=self.user, organization=self.org)
        self.assertTrue(coach.is_active)

    def test_coach_optional_fields_default_to_empty(self):
        coach = Coach.objects.create(user=self.user, organization=self.org)
        self.assertEqual(coach.bio, "")
        self.assertEqual(coach.certifications, "")
        self.assertEqual(coach.specialties, "")
        self.assertEqual(coach.years_experience, 0)

    def test_coach_optional_fields_can_be_set(self):
        coach = Coach.objects.create(
            user=self.user,
            organization=self.org,
            bio="Trail running specialist",
            certifications="NASM CPT, UESCA",
            specialties="trail, ultra",
            years_experience=8,
        )
        self.assertEqual(coach.bio, "Trail running specialist")
        self.assertEqual(coach.years_experience, 8)

    def test_one_active_coach_per_user_per_org(self):
        Coach.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Coach.objects.create(user=self.user, organization=self.org)

    def test_two_inactive_coaches_allowed(self):
        Coach.objects.create(user=self.user, organization=self.org, is_active=False)
        coach2 = Coach.objects.create(user=self.user, organization=self.org, is_active=False)
        self.assertFalse(coach2.is_active)

    def test_coach_in_multiple_organizations_allowed(self):
        org2 = _make_org("other-coach-org")
        c1 = Coach.objects.create(user=self.user, organization=self.org)
        c2 = Coach.objects.create(user=self.user, organization=org2)
        self.assertEqual(c1.organization, self.org)
        self.assertEqual(c2.organization, org2)

    def test_coach_str(self):
        coach = Coach(user=self.user, organization=self.org)
        result = str(coach)
        self.assertIn("Coach:", result)

    def test_coach_cascade_deletes_with_organization(self):
        Coach.objects.create(user=self.user, organization=self.org)
        self.assertEqual(Coach.objects.filter(organization=self.org).count(), 1)
        self.org.delete()
        self.assertEqual(Coach.objects.count(), 0)

    def test_coach_timestamps_set_on_creation(self):
        coach = Coach.objects.create(user=self.user, organization=self.org)
        self.assertIsNotNone(coach.created_at)
        self.assertIsNotNone(coach.updated_at)


class AthleteModelTests(TestCase):
    def setUp(self):
        self.user = _make_user("athlete_user")
        self.org = _make_org("athlete-org")

    def test_athlete_requires_organization(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertEqual(athlete.organization, self.org)
        self.assertEqual(athlete.user, self.user)

    def test_athlete_is_active_defaults_to_true(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertTrue(athlete.is_active)

    def test_athlete_notes_defaults_to_empty(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertEqual(athlete.notes, "")

    def test_one_active_athlete_per_user_per_org(self):
        Athlete.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Athlete.objects.create(user=self.user, organization=self.org)

    def test_two_inactive_athletes_allowed(self):
        Athlete.objects.create(user=self.user, organization=self.org, is_active=False)
        a2 = Athlete.objects.create(user=self.user, organization=self.org, is_active=False)
        self.assertFalse(a2.is_active)

    def test_athlete_optional_team_assignment(self):
        team = Team.objects.create(organization=self.org, name="Elite Squad")
        athlete = Athlete.objects.create(
            user=self.user, organization=self.org, team=team
        )
        self.assertEqual(athlete.team, team)

    def test_athlete_team_nullable(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertIsNone(athlete.team)

    def test_athlete_coach_nullable(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertIsNone(athlete.coach)

    def test_athlete_coach_assignment(self):
        coach_user = _make_user("the_coach")
        coach = Coach.objects.create(user=coach_user, organization=self.org)
        athlete = Athlete.objects.create(
            user=self.user, organization=self.org, coach=coach
        )
        self.assertEqual(athlete.coach, coach)

    def test_athlete_coach_set_null_on_coach_delete(self):
        coach_user = _make_user("coach_del")
        coach = Coach.objects.create(user=coach_user, organization=self.org)
        athlete = Athlete.objects.create(
            user=self.user, organization=self.org, coach=coach
        )
        coach.delete()
        athlete.refresh_from_db()
        self.assertIsNone(athlete.coach)

    def test_athlete_organization_cascade_delete(self):
        Athlete.objects.create(user=self.user, organization=self.org)
        self.assertEqual(Athlete.objects.filter(organization=self.org).count(), 1)
        self.org.delete()
        self.assertEqual(Athlete.objects.count(), 0)

    def test_athlete_str(self):
        athlete = Athlete(user=self.user, organization=self.org)
        result = str(athlete)
        self.assertIn("Athlete:", result)

    def test_athlete_timestamps_set_on_creation(self):
        athlete = Athlete.objects.create(user=self.user, organization=self.org)
        self.assertIsNotNone(athlete.created_at)
        self.assertIsNotNone(athlete.updated_at)


class OrganizationConsistencyTests(TestCase):
    """
    Verify that Coach and Athlete are correctly organization-scoped.
    Queries must always filter by organization — cross-org access must be
    structurally impossible at the model layer.
    """

    def setUp(self):
        self.org_a = _make_org("org-a")
        self.org_b = _make_org("org-b")
        self.user = _make_user("consistency_user")

    def test_coach_scoped_to_organization(self):
        Coach.objects.create(user=self.user, organization=self.org_a)
        self.assertEqual(Coach.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(Coach.objects.filter(organization=self.org_b).count(), 0)

    def test_athlete_scoped_to_organization(self):
        Athlete.objects.create(user=self.user, organization=self.org_a)
        self.assertEqual(Athlete.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(Athlete.objects.filter(organization=self.org_b).count(), 0)

    def test_team_belongs_to_same_org_as_athlete(self):
        team_a = Team.objects.create(organization=self.org_a, name="Team A")
        user2 = _make_user("athlete_org_b")
        # Athlete in org_b assigned to team from org_a — structurally possible
        # at model level (no DB-level cross-org FK constraint here).
        # Business logic enforcement is at the service layer (PR-104+).
        athlete = Athlete.objects.create(
            user=user2, organization=self.org_b, team=team_a
        )
        # Document: model accepts it; service must validate same-org rule.
        self.assertEqual(athlete.team, team_a)


class LegacyCoexistenceTests(TestCase):
    """
    Verify that the legacy Alumno model is completely unaffected by PR-103.
    This test protects against accidental breakage of the legacy data layer.
    """

    def test_alumno_model_unaffected(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        coach_user = User.objects.create_user(username="legacy_coach", password="x")
        alumno = Alumno.objects.create(
            nombre="Carlos",
            apellido="Ruiz",
            entrenador=coach_user,
        )
        fetched = Alumno.objects.get(id=alumno.id)
        self.assertEqual(fetched.nombre, "Carlos")
        self.assertEqual(fetched.entrenador, coach_user)

    def test_coach_and_alumno_independent(self):
        """Coach model existence does not interfere with Alumno."""
        coach_user = _make_user("dual_coach")
        org = _make_org("dual-org")
        Coach.objects.create(user=coach_user, organization=org)
        alumno = Alumno.objects.create(
            nombre="Ana",
            apellido="Lopez",
            entrenador=coach_user,
        )
        self.assertEqual(Alumno.objects.filter(entrenador=coach_user).count(), 1)
        self.assertEqual(Coach.objects.filter(user=coach_user).count(), 1)
