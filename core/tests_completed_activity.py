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

from core.models import Alumno, Actividad, CompletedActivity, ActivityStream, Organization, Athlete

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


# ===========================================================================
# PR-114: Plan ≠ Real execution-side invariant tests
# ===========================================================================

class PlanNotRealExecutionTests(TestCase):
    """
    Enforce the Plan ≠ Real invariant on CompletedActivity.

    If any test here needs to be removed to accommodate a feature,
    that feature violates the domain law and must be redesigned.
    """

    def test_completed_activity_has_no_duration_target_field(self):
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        self.assertNotIn("duration_target", field_names)
        self.assertNotIn("duration_target_s", field_names)

    def test_completed_activity_has_no_distance_target_field(self):
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        self.assertNotIn("distance_target", field_names)
        self.assertNotIn("distance_target_m", field_names)

    def test_completed_activity_has_no_planned_workout_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in CompletedActivity._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("PlannedWorkout", fk_targets)
        self.assertNotIn("Entrenamiento", fk_targets)

    def test_completed_activity_has_no_workout_assignment_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in CompletedActivity._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("WorkoutAssignment", fk_targets)

    def test_completed_activity_has_no_actual_prefix_on_planning_fields(self):
        """No planning-side target fields exist under any naming pattern."""
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        for name in field_names:
            self.assertFalse(
                name.endswith("_target"),
                f"Found target field on CompletedActivity: {name}",
            )

    def test_activity_stream_has_no_planned_workout_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in ActivityStream._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("PlannedWorkout", fk_targets)
        self.assertNotIn("WorkoutAssignment", fk_targets)
        self.assertNotIn("Entrenamiento", fk_targets)


# ===========================================================================
# PR-114: Provider boundary tests
# ===========================================================================

class ProviderBoundaryTests(TestCase):
    """
    Enforce provider isolation at the model layer.
    """

    def test_provider_field_is_char_not_fk(self):
        """
        CompletedActivity.provider must be a CharField (string slug), not a FK.
        This ensures the domain model is decoupled from the integration layer.
        """
        field = CompletedActivity._meta.get_field("provider")
        self.assertEqual(field.get_internal_type(), "CharField")

    def test_raw_payload_is_json_field(self):
        """raw_payload preserves provider-native data for audit/re-processing."""
        field = CompletedActivity._meta.get_field("raw_payload")
        self.assertEqual(field.get_internal_type(), "JSONField")

    def test_activity_stream_provider_is_char_not_fk(self):
        """ActivityStream.provider must be a CharField, never a FK to a registry."""
        field = ActivityStream._meta.get_field("provider")
        self.assertEqual(field.get_internal_type(), "CharField")

    def test_activity_stream_payload_is_json_field(self):
        """ActivityStream.payload is a JSONField for flexible event payloads."""
        field = ActivityStream._meta.get_field("payload")
        self.assertEqual(field.get_internal_type(), "JSONField")


# ===========================================================================
# PR-114: Athlete bridge (nullable FK added to CompletedActivity)
# ===========================================================================

def _make_domain_org(name="DomainOrg"):
    return Organization.objects.create(name=name, slug=name.lower().replace(" ", "-"))


def _make_domain_athlete(org, username="domain_ath"):
    user = User.objects.create_user(username=username, password="x")
    return Athlete.objects.create(user=user, organization=org)


class AthleteBridgeTests(TestCase):
    """
    Tests for the nullable athlete FK added to CompletedActivity in PR-114.

    Both alumno (legacy) and athlete (new domain) coexist.
    No backfill is required or performed in this PR.
    """

    def setUp(self):
        self.org_user = _make_org("bridge_coach")
        self.alumno = _make_alumno(self.org_user)
        self.domain_org = _make_domain_org("BridgeOrg")
        self.athlete = _make_domain_athlete(self.domain_org, username="bridge_ath")

    def test_athlete_field_is_nullable(self):
        """CompletedActivity can be created without setting athlete."""
        act = _make_activity(self.org_user, self.alumno, provider_activity_id="br-001")
        self.assertIsNone(act.athlete)

    def test_athlete_field_can_be_set(self):
        """CompletedActivity accepts an Athlete FK alongside legacy alumno."""
        act = _make_activity(
            self.org_user, self.alumno,
            provider_activity_id="br-002",
            athlete=self.athlete,
        )
        act.refresh_from_db()
        self.assertEqual(act.athlete, self.athlete)

    def test_legacy_alumno_unchanged_when_athlete_set(self):
        """Setting athlete does not change or nullify the legacy alumno FK."""
        act = _make_activity(
            self.org_user, self.alumno,
            provider_activity_id="br-003",
            athlete=self.athlete,
        )
        act.refresh_from_db()
        self.assertEqual(act.alumno, self.alumno)
        self.assertEqual(act.athlete, self.athlete)

    def test_athlete_set_null_on_athlete_delete(self):
        """Deleting the Athlete nullifies the FK on CompletedActivity (SET_NULL)."""
        act = _make_activity(
            self.org_user, self.alumno,
            provider_activity_id="br-004",
            athlete=self.athlete,
        )
        self.athlete.delete()
        act.refresh_from_db()
        self.assertIsNone(act.athlete)
        # alumno remains intact
        self.assertIsNotNone(act.alumno_id)

    def test_activity_without_athlete_still_provides_all_data(self):
        """Legacy path: activity with alumno but no athlete is fully functional."""
        act = _make_activity(
            self.org_user, self.alumno,
            provider_activity_id="br-005",
            elevation_gain_m=300.0,
            raw_payload={"name": "Trail Run"},
        )
        self.assertEqual(act.sport, "RUN")
        self.assertAlmostEqual(act.elevation_gain_m, 300.0)
        self.assertIsNone(act.athlete)


# ===========================================================================
# PR-114: ActivityStream tests
# ===========================================================================

class ActivityStreamCreationTests(TestCase):

    def setUp(self):
        self.org_user = _make_org("stream_coach")
        self.alumno = _make_alumno(self.org_user)
        self.activity = _make_activity(
            self.org_user, self.alumno, provider_activity_id="stream-001"
        )

    def test_basic_creation(self):
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={"raw_bytes": 1024},
        )
        self.assertIsNotNone(stream.pk)
        self.assertEqual(stream.completed_activity, self.activity)
        self.assertEqual(stream.stream_type, "ingest")

    def test_payload_stores_arbitrary_json(self):
        payload = {"source": "strava", "fields": ["distance", "hr"], "count": 42}
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.NORMALIZED,
            payload=payload,
        )
        stream.refresh_from_db()
        self.assertEqual(stream.payload["source"], "strava")
        self.assertEqual(stream.payload["count"], 42)

    def test_provider_field_stored(self):
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            provider="strava",
            payload={},
        )
        self.assertEqual(stream.provider, "strava")

    def test_provider_blank_by_default(self):
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.CUSTOM,
            payload={"note": "manual"},
        )
        self.assertEqual(stream.provider, "")

    def test_created_at_auto_set(self):
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.METRIC_SNAPSHOT,
            payload={},
        )
        self.assertIsNotNone(stream.created_at)

    def test_str_includes_stream_type_and_activity(self):
        stream = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={},
        )
        s = str(stream)
        self.assertIn("ingest", s)
        self.assertIn(str(self.activity.pk), s)


class ActivityStreamTypeTests(TestCase):

    def setUp(self):
        self.org_user = _make_org("type_coach")
        self.alumno = _make_alumno(self.org_user)
        self.activity = _make_activity(
            self.org_user, self.alumno, provider_activity_id="type-001"
        )

    def test_all_stream_type_choices_accepted(self):
        for i, (choice_value, _) in enumerate(ActivityStream.StreamType.choices):
            ActivityStream.objects.create(
                completed_activity=self.activity,
                stream_type=choice_value,
                payload={"seq": i},
            )

    def test_multiple_records_same_stream_type_allowed(self):
        """Event streams allow multiple INGEST entries per activity (re-ingestion)."""
        ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={"attempt": 1},
        )
        # Second INGEST for the same activity must NOT raise
        s2 = ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={"attempt": 2},
        )
        self.assertIsNotNone(s2.pk)

    def test_ordering_is_most_recent_first(self):
        """ActivityStream ordering = ['-created_at']."""
        ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={"seq": 1},
        )
        ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.NORMALIZED,
            payload={"seq": 2},
        )
        streams = list(ActivityStream.objects.filter(completed_activity=self.activity))
        # Most recent first
        self.assertEqual(streams[0].stream_type, "normalized")
        self.assertEqual(streams[1].stream_type, "ingest")


class ActivityStreamCascadeTests(TestCase):

    def setUp(self):
        self.org_user = _make_org("cascade_coach")
        self.alumno = _make_alumno(self.org_user)
        self.activity = _make_activity(
            self.org_user, self.alumno, provider_activity_id="cascade-001"
        )

    def test_streams_cascade_delete_with_activity(self):
        ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.INGEST,
            payload={},
        )
        ActivityStream.objects.create(
            completed_activity=self.activity,
            stream_type=ActivityStream.StreamType.NORMALIZED,
            payload={},
        )
        activity_id = self.activity.pk
        self.activity.delete()
        self.assertFalse(
            ActivityStream.objects.filter(completed_activity_id=activity_id).exists()
        )


# ===========================================================================
# PR-114: Idempotency constraint verification
# ===========================================================================

class IdempotencyTests(TestCase):
    """
    Verify the (organization, provider, provider_activity_id) unique constraint.
    These tests should already pass with the pre-existing model, but are
    explicitly named here as required by the capsule definition-of-done.
    """

    def setUp(self):
        self.org = _make_org("idem_coach")
        self.alumno = _make_alumno(self.org)

    def test_duplicate_activity_same_provider_raises(self):
        _make_activity(self.org, self.alumno, provider_activity_id="idem-001")
        with self.assertRaises(IntegrityError):
            _make_activity(self.org, self.alumno, provider_activity_id="idem-001")

    def test_same_provider_id_different_org_allowed(self):
        org2 = _make_org("idem_coach_2")
        alumno2 = _make_alumno(org2, n=2)
        _make_activity(self.org, self.alumno, provider_activity_id="shared-idem")
        act2 = _make_activity(org2, alumno2, provider_activity_id="shared-idem")
        self.assertIsNotNone(act2.pk)

    def test_idempotency_constraint_name(self):
        constraint_names = [
            c.name for c in CompletedActivity._meta.constraints
        ]
        self.assertIn("uniq_completed_activity_org_provider_id", constraint_names)


# ===========================================================================
# PR-114: Legacy coexistence
# ===========================================================================

class LegacyCoexistenceTests(TestCase):
    """
    Verify that legacy structures remain intact alongside PR-114 additions.
    """

    def test_actividad_model_exists_with_legacy_fields(self):
        """Verify legacy Actividad model is untouched."""
        field_names = [f.name for f in Actividad._meta.get_fields()]
        # Key legacy fields that must still exist
        self.assertIn("usuario", field_names)
        self.assertIn("tipo_deporte", field_names)
        self.assertIn("fecha_inicio", field_names)

    def test_completed_activity_alumno_still_required(self):
        """Legacy alumno FK is still present and non-nullable."""
        field = CompletedActivity._meta.get_field("alumno")
        self.assertFalse(field.null)

    def test_completed_activity_athlete_is_nullable(self):
        """New athlete FK is nullable (backward-compatible bridge)."""
        field = CompletedActivity._meta.get_field("athlete")
        self.assertTrue(field.null)

    def test_both_alumno_and_athlete_coexist_on_model(self):
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        self.assertIn("alumno", field_names)
        self.assertIn("athlete", field_names)

    def test_completed_activity_creation_without_athlete_still_works(self):
        """Legacy path: creating CompletedActivity with only alumno still works."""
        org = _make_org("legacy_coach")
        alumno = _make_alumno(org)
        act = _make_activity(org, alumno, provider_activity_id="legacy-001")
        self.assertIsNone(act.athlete)
        self.assertIsNotNone(act.alumno_id)
