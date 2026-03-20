"""
core/tests_pr126_org_fk_migration.py

PR-126: CompletedActivity.organization FK → Organization (D2 fix).

Coverage
--------
1. organization field is a FK to Organization (not User).
2. get_or_create is idempotent with the new Organization FK.
3. Suunto ingest resolves Organization via Membership (not alumno.entrenador).
4. Cross-org isolation: activity of org A is invisible from org B.
5. Suunto ingest raises ValueError when entrenador has no active Membership.
"""

import datetime
import unittest

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    Alumno,
    CompletedActivity,
    Membership,
    Organization,
)

User = get_user_model()

_T0 = datetime.datetime(2026, 3, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role="coach"):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _make_alumno(coach_user, athlete_user=None, n=1):
    return Alumno.objects.create(
        entrenador=coach_user,
        usuario=athlete_user,
        nombre=f"Atleta{n}",
        apellido="PR126",
        email=f"atleta{n}_pr126_{coach_user.pk}@test.com",
    )


def _make_activity(org, alumno, provider_activity_id="pr126-act-001", **overrides):
    defaults = dict(
        organization=org,
        alumno=alumno,
        sport="RUN",
        start_time=_T0,
        duration_s=3600,
        distance_m=10000.0,
        provider=CompletedActivity.Provider.STRAVA,
        provider_activity_id=provider_activity_id,
    )
    defaults.update(overrides)
    return CompletedActivity.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Test 1: organization FK points to Organization, not User
# ---------------------------------------------------------------------------

class OrgFKTypeTests(TestCase):

    def test_organization_field_references_organization_model(self):
        """CompletedActivity.organization must be a FK to Organization, not User."""
        field = CompletedActivity._meta.get_field("organization")
        self.assertEqual(field.related_model.__name__, "Organization")

    def test_organization_field_is_non_nullable(self):
        """Fail-closed: organization is required on every CompletedActivity row."""
        field = CompletedActivity._meta.get_field("organization")
        self.assertFalse(field.null)

    def test_create_activity_with_organization_instance(self):
        org = _make_org("pr126-org-1")
        coach = _make_user("pr126-coach-1")
        _make_membership(coach, org)
        alumno = _make_alumno(coach)

        act = _make_activity(org, alumno)

        act.refresh_from_db()
        self.assertIsInstance(act.organization, Organization)
        self.assertEqual(act.organization, org)


# ---------------------------------------------------------------------------
# Test 2: get_or_create idempotency with Organization FK
# ---------------------------------------------------------------------------

class OrgFKIdempotencyTests(TestCase):

    def setUp(self):
        self.org = _make_org("pr126-idem-org")
        self.coach = _make_user("pr126-idem-coach")
        _make_membership(self.coach, self.org)
        self.alumno = _make_alumno(self.coach)

    def test_get_or_create_idempotent(self):
        """Calling get_or_create twice with same (org, provider, provider_activity_id)
        yields exactly one row (idempotent)."""
        defaults = {
            "alumno": self.alumno,
            "sport": "RUN",
            "start_time": _T0,
            "duration_s": 3600,
            "distance_m": 10000.0,
        }
        act1, created1 = CompletedActivity.objects.get_or_create(
            organization=self.org,
            provider=CompletedActivity.Provider.SUUNTO,
            provider_activity_id="idem-suunto-001",
            defaults=defaults,
        )
        act2, created2 = CompletedActivity.objects.get_or_create(
            organization=self.org,
            provider=CompletedActivity.Provider.SUUNTO,
            provider_activity_id="idem-suunto-001",
            defaults=defaults,
        )

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(act1.pk, act2.pk)
        self.assertEqual(
            CompletedActivity.objects.filter(
                organization=self.org,
                provider_activity_id="idem-suunto-001",
            ).count(),
            1,
        )

    def test_duplicate_create_raises_integrity_error(self):
        _make_activity(self.org, self.alumno, provider_activity_id="dup-pr126")
        with self.assertRaises(IntegrityError):
            _make_activity(self.org, self.alumno, provider_activity_id="dup-pr126")


# ---------------------------------------------------------------------------
# Test 3: Suunto ingest resolves Organization via Membership
# ---------------------------------------------------------------------------

class SuuntoIngestOrgResolutionTests(TestCase):

    def setUp(self):
        self.org = _make_org("pr126-suunto-org")
        self.coach = _make_user("pr126-suunto-coach")
        _make_membership(self.coach, self.org, role="coach")
        self.alumno = _make_alumno(self.coach)

    def test_ingest_creates_activity_linked_to_organization(self):
        """ingest_suunto_workout must link CompletedActivity to Organization, not User."""
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        fit_data = {
            "start_date": _T0,
            "duration_s": 1800,
            "sport": "RUN",
            "distance_m": 5000.0,
        }
        activity, created = ingest_suunto_workout(
            alumno_id=self.alumno.pk,
            external_workout_id="suunto-wk-pr126-001",
            fit_data=fit_data,
        )

        self.assertTrue(created)
        activity.refresh_from_db()
        self.assertIsInstance(activity.organization, Organization)
        self.assertEqual(activity.organization, self.org)

    def test_ingest_idempotent_with_organization_fk(self):
        """Second ingest with same workoutKey is a noop (idempotent)."""
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        fit_data = {"start_date": _T0, "duration_s": 1800, "sport": "RUN"}
        ingest_suunto_workout(
            alumno_id=self.alumno.pk,
            external_workout_id="suunto-wk-pr126-dup",
            fit_data=fit_data,
        )
        _, created2 = ingest_suunto_workout(
            alumno_id=self.alumno.pk,
            external_workout_id="suunto-wk-pr126-dup",
            fit_data=fit_data,
        )
        self.assertFalse(created2)
        self.assertEqual(
            CompletedActivity.objects.filter(
                provider_activity_id="suunto-wk-pr126-dup"
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# Test 4: Cross-org isolation
# ---------------------------------------------------------------------------

class CrossOrgIsolationTests(TestCase):

    def setUp(self):
        self.org_a = _make_org("pr126-iso-org-a")
        self.coach_a = _make_user("pr126-iso-coach-a")
        _make_membership(self.coach_a, self.org_a)
        self.alumno_a = _make_alumno(self.coach_a, n=1)

        self.org_b = _make_org("pr126-iso-org-b")
        self.coach_b = _make_user("pr126-iso-coach-b")
        _make_membership(self.coach_b, self.org_b)
        self.alumno_b = _make_alumno(self.coach_b, n=2)

    def test_activity_org_a_not_visible_from_org_b(self):
        """Activity owned by org A must not appear in org B's queryset."""
        _make_activity(self.org_a, self.alumno_a, provider_activity_id="iso-act-a")

        count_b = CompletedActivity.objects.filter(organization=self.org_b).count()
        self.assertEqual(count_b, 0)

    def test_same_provider_activity_id_allowed_across_orgs(self):
        """Unique constraint is per-org: same provider_activity_id is fine in two orgs."""
        _make_activity(self.org_a, self.alumno_a, provider_activity_id="shared-iso-id")
        act_b = _make_activity(self.org_b, self.alumno_b, provider_activity_id="shared-iso-id")
        self.assertIsNotNone(act_b.pk)

    def test_org_a_queryset_excludes_org_b_activities(self):
        _make_activity(self.org_a, self.alumno_a, provider_activity_id="only-a")
        _make_activity(self.org_b, self.alumno_b, provider_activity_id="only-b")

        qs_a = CompletedActivity.objects.filter(organization=self.org_a)
        self.assertEqual(qs_a.count(), 1)
        self.assertEqual(qs_a.first().provider_activity_id, "only-a")


# ---------------------------------------------------------------------------
# Test 5: Suunto ingest raises when entrenador has no active Membership
# ---------------------------------------------------------------------------

class SuuntoIngestNoMembershipTests(TestCase):

    def test_ingest_raises_value_error_when_no_membership(self):
        """If the coach has no active Membership, ingest must raise ValueError."""
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        # Coach user exists but has NO Membership
        coach_no_org = _make_user("pr126-nomem-coach")
        alumno = _make_alumno(coach_no_org)

        fit_data = {"start_date": _T0, "duration_s": 1800, "sport": "RUN"}
        with self.assertRaises(ValueError) as ctx:
            ingest_suunto_workout(
                alumno_id=alumno.pk,
                external_workout_id="suunto-no-mem",
                fit_data=fit_data,
            )
        self.assertIn("Membership", str(ctx.exception))

    def test_ingest_raises_value_error_when_no_entrenador(self):
        """If alumno has no entrenador at all, ingest must raise ValueError."""
        from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

        alumno_no_coach = Alumno.objects.create(
            entrenador=None,
            nombre="NoCoach",
            apellido="PR126",
        )
        fit_data = {"start_date": _T0, "duration_s": 1800, "sport": "RUN"}
        with self.assertRaises(ValueError) as ctx:
            ingest_suunto_workout(
                alumno_id=alumno_no_coach.pk,
                external_workout_id="suunto-no-coach",
                fit_data=fit_data,
            )
        self.assertIn("entrenador", str(ctx.exception))
