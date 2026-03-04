"""
Tests for CompletedActivity model (PR-B foundation).

Coverage
--------
- Happy-path creation with all required fields.
- Unique constraint on (organization, provider, provider_activity_id).
- Multi-tenant isolation: same provider_activity_id is allowed across orgs.
- elevation_gain_m is nullable (data not always available).
- plan ≠ real: CompletedActivity has no reference to Entrenamiento.
"""

import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from core.models import Alumno, CompletedActivity

User = get_user_model()

_T0 = datetime.datetime(2026, 3, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)


def _make_org(username):
    return User.objects.create_user(username=username, password="x")


def _make_alumno(org, n=1):
    return Alumno.objects.create(
        entrenador=org,
        nombre=f"Atleta{n}",
        apellido="Test",
        email=f"atleta{n}_{org.username}@test.com",
    )


def _make_activity(org, alumno, provider_activity_id="act-001", **overrides):
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


class CompletedActivityCreationTests(TestCase):
    def setUp(self):
        self.org = _make_org("coach_ca_01")
        self.alumno = _make_alumno(self.org)

    def test_create_minimal(self):
        act = _make_activity(self.org, self.alumno)
        self.assertIsNotNone(act.pk)
        self.assertEqual(act.organization, self.org)
        self.assertEqual(act.alumno, self.alumno)
        self.assertEqual(act.sport, "RUN")
        self.assertEqual(act.provider, "strava")
        self.assertEqual(act.provider_activity_id, "act-001")
        self.assertEqual(act.duration_s, 3600)
        self.assertAlmostEqual(act.distance_m, 10000.0)
        self.assertIsNotNone(act.created_at)

    def test_elevation_gain_nullable(self):
        act = _make_activity(self.org, self.alumno, provider_activity_id="act-002")
        self.assertIsNone(act.elevation_gain_m)

    def test_elevation_gain_stored(self):
        act = _make_activity(
            self.org, self.alumno,
            provider_activity_id="act-003",
            elevation_gain_m=450.5,
        )
        self.assertAlmostEqual(act.elevation_gain_m, 450.5)

    def test_raw_payload_default_empty_dict(self):
        act = _make_activity(self.org, self.alumno, provider_activity_id="act-004")
        self.assertEqual(act.raw_payload, {})

    def test_raw_payload_stored(self):
        payload = {"name": "Morning Run", "kudos_count": 5}
        act = _make_activity(
            self.org, self.alumno,
            provider_activity_id="act-005",
            raw_payload=payload,
        )
        act.refresh_from_db()
        self.assertEqual(act.raw_payload["name"], "Morning Run")

    def test_str_representation(self):
        act = _make_activity(self.org, self.alumno)
        s = str(act)
        self.assertIn("RUN", s)
        self.assertIn("strava", s)
        self.assertIn("act-001", s)

    def test_plan_not_real_no_entrenamiento_field(self):
        """CompletedActivity must not reference Entrenamiento (plan ≠ real)."""
        self.assertFalse(hasattr(CompletedActivity, "entrenamiento"))


class CompletedActivityUniqueConstraintTests(TestCase):
    def setUp(self):
        self.org = _make_org("coach_ca_02")
        self.alumno = _make_alumno(self.org)

    def test_duplicate_raises_integrity_error(self):
        _make_activity(self.org, self.alumno, provider_activity_id="dup-001")
        with self.assertRaises(IntegrityError):
            _make_activity(self.org, self.alumno, provider_activity_id="dup-001")

    def test_same_id_different_provider_allowed(self):
        _make_activity(
            self.org, self.alumno,
            provider=CompletedActivity.Provider.STRAVA,
            provider_activity_id="shared-id-1",
        )
        # Same org, same provider_activity_id, but different provider → should succeed.
        act2 = _make_activity(
            self.org, self.alumno,
            provider=CompletedActivity.Provider.GARMIN,
            provider_activity_id="shared-id-1",
        )
        self.assertIsNotNone(act2.pk)

    def test_same_id_different_org_allowed(self):
        """Two coaches can both have an activity with the same provider id."""
        org2 = _make_org("coach_ca_03")
        alumno2 = _make_alumno(org2, n=2)
        _make_activity(self.org, self.alumno, provider_activity_id="cross-org-id")
        act2 = _make_activity(org2, alumno2, provider_activity_id="cross-org-id")
        self.assertIsNotNone(act2.pk)

    def test_different_id_same_org_allowed(self):
        _make_activity(self.org, self.alumno, provider_activity_id="id-A")
        act2 = _make_activity(self.org, self.alumno, provider_activity_id="id-B")
        self.assertIsNotNone(act2.pk)


class CompletedActivityTenantTests(TestCase):
    """Verify that organization field is always required (fail-closed)."""

    def setUp(self):
        self.org = _make_org("coach_ca_04")
        self.alumno = _make_alumno(self.org)

    def test_organization_required(self):
        with self.assertRaises((IntegrityError, Exception)):
            CompletedActivity.objects.create(
                organization=None,
                alumno=self.alumno,
                sport="RUN",
                start_time=_T0,
                duration_s=1800,
                distance_m=5000,
                provider="strava",
                provider_activity_id="no-org-id",
            )
