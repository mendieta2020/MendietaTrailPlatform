"""
core/tests_race_event.py

Tests for RaceEvent domain model (PR-106).

RaceEvent is an organization-scoped competition catalog entry.
It is the canonical FK target for AthleteGoal.target_event (implemented
in PR-105, wired up once this model exists).

Covers:
- Model creation with required fields
- Optional fields allowed to be blank/null
- Cross-organization: same name+date allowed in different orgs
- Within same org: duplicate name+date blocked (UniqueConstraint)
- Cascade delete with organization
- String representation
- Discipline choices
- No dependency on legacy Carrera model
"""
import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .models import Organization, RaceEvent

User = get_user_model()


def _org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _event(org, name="UTMB 2026", discipline="trail", event_date=None, **kwargs):
    if event_date is None:
        event_date = datetime.date(2026, 8, 28)
    return RaceEvent.objects.create(
        organization=org,
        name=name,
        discipline=discipline,
        event_date=event_date,
        **kwargs,
    )


class RaceEventCreationTests(TestCase):
    def setUp(self):
        self.org = _org("creation-org")

    def test_race_event_requires_organization_name_discipline_date(self):
        event = _event(self.org)
        self.assertEqual(event.organization, self.org)
        self.assertEqual(event.name, "UTMB 2026")
        self.assertEqual(event.discipline, "trail")
        self.assertEqual(event.event_date, datetime.date(2026, 8, 28))

    def test_optional_fields_are_empty_or_null_by_default(self):
        event = _event(self.org)
        self.assertEqual(event.location, "")
        self.assertEqual(event.country, "")
        self.assertIsNone(event.distance_km)
        self.assertIsNone(event.elevation_gain_m)
        self.assertEqual(event.event_url, "")
        self.assertEqual(event.notes, "")
        self.assertIsNone(event.created_by)

    def test_optional_fields_can_be_set(self):
        event = _event(
            self.org,
            location="Chamonix",
            country="France",
            distance_km=171.0,
            elevation_gain_m=10000.0,
            event_url="https://utmb.world/utmb",
            notes="A-race for the season.",
        )
        self.assertEqual(event.location, "Chamonix")
        self.assertEqual(event.country, "France")
        self.assertAlmostEqual(event.distance_km, 171.0)
        self.assertAlmostEqual(event.elevation_gain_m, 10000.0)
        self.assertEqual(event.event_url, "https://utmb.world/utmb")
        self.assertEqual(event.notes, "A-race for the season.")

    def test_created_by_can_be_set(self):
        user = _user("race_creator")
        event = _event(self.org, created_by=user)
        self.assertEqual(event.created_by, user)

    def test_timestamps_set_on_creation(self):
        event = _event(self.org)
        self.assertIsNotNone(event.created_at)
        self.assertIsNotNone(event.updated_at)

    def test_str_includes_name_and_date(self):
        event = _event(self.org, name="Lavaredo Ultra Trail")
        result = str(event)
        self.assertIn("Lavaredo Ultra Trail", result)
        self.assertIn("2026-08-28", result)


class RaceEventDisciplineTests(TestCase):
    def setUp(self):
        self.org = _org("disc-org")

    def test_discipline_choices_cover_endurance_domain(self):
        valid = [c[0] for c in RaceEvent.Discipline.choices]
        self.assertIn("run", valid)
        self.assertIn("trail", valid)
        self.assertIn("bike", valid)
        self.assertIn("swim", valid)
        self.assertIn("triathlon", valid)
        self.assertIn("other", valid)

    def test_each_discipline_can_be_saved(self):
        base_date = datetime.date(2026, 6, 1)
        for i, (disc, _) in enumerate(RaceEvent.Discipline.choices):
            event = RaceEvent.objects.create(
                organization=self.org,
                name=f"Event {disc}",
                discipline=disc,
                event_date=base_date + datetime.timedelta(days=i),
            )
            self.assertEqual(event.discipline, disc)


class RaceEventTenancyTests(TestCase):
    def setUp(self):
        self.org_a = _org("tenancy-org-a")
        self.org_b = _org("tenancy-org-b")

    def test_same_name_and_date_allowed_across_different_organizations(self):
        """Organization-scoped catalog: two orgs may each track the same race."""
        e1 = _event(self.org_a, name="UTMB 2026")
        e2 = _event(self.org_b, name="UTMB 2026")
        self.assertEqual(e1.name, e2.name)
        self.assertEqual(e1.event_date, e2.event_date)
        self.assertNotEqual(e1.organization, e2.organization)

    def test_duplicate_name_and_date_within_same_org_is_blocked(self):
        """UniqueConstraint: org + name + event_date must be unique."""
        _event(self.org_a, name="UTMB 2026")
        with self.assertRaises(IntegrityError):
            _event(self.org_a, name="UTMB 2026")

    def test_same_name_different_date_within_org_is_allowed(self):
        e1 = _event(self.org_a, name="Buff Epic Trail", event_date=datetime.date(2026, 7, 10))
        e2 = _event(self.org_a, name="Buff Epic Trail", event_date=datetime.date(2027, 7, 10))
        self.assertNotEqual(e1.event_date, e2.event_date)

    def test_cascade_delete_with_organization(self):
        _event(self.org_a)
        self.assertEqual(RaceEvent.objects.filter(organization=self.org_a).count(), 1)
        self.org_a.delete()
        self.assertEqual(RaceEvent.objects.count(), 0)

    def test_race_events_scoped_to_organization(self):
        _event(self.org_a, name="Race A")
        _event(self.org_b, name="Race B")
        self.assertEqual(RaceEvent.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(RaceEvent.objects.filter(organization=self.org_b).count(), 1)


class RaceEventOrderingTests(TestCase):
    def setUp(self):
        self.org = _org("order-org")

    def test_events_ordered_by_event_date_ascending(self):
        _event(self.org, name="Race C", event_date=datetime.date(2026, 12, 1))
        _event(self.org, name="Race A", event_date=datetime.date(2026, 3, 1))
        _event(self.org, name="Race B", event_date=datetime.date(2026, 7, 1))
        events = list(RaceEvent.objects.filter(organization=self.org))
        dates = [e.event_date for e in events]
        self.assertEqual(dates, sorted(dates))


class RaceEventLegacyIndependenceTests(TestCase):
    """
    RaceEvent must have zero dependency on the legacy Carrera model.
    This test verifies structural independence.
    """

    def test_race_event_has_no_carrera_dependency(self):
        from .models import Carrera
        # RaceEvent fields must not reference Carrera
        race_event_fields = {f.name for f in RaceEvent._meta.get_fields()}
        self.assertNotIn("carrera", race_event_fields)
        # Both models can exist independently in the same app
        org = _org("legacy-independence-org")
        event = _event(org)
        self.assertIsNotNone(event.pk)
        # Carrera table still accessible — no coupling
        self.assertEqual(Carrera.objects.count(), 0)
