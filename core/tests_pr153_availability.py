"""
core/tests_pr153_availability.py

Tests for AthleteAvailabilityListView.bulk_update (PUT endpoint).

Coverage:
- PUT replaces all existing records atomically (happy path)
- Unauthenticated actor is rejected (401)
- Actor from org-B cannot PUT against org-A athlete's availability (403/404)
- Empty payload clears all records
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Athlete, AthleteAvailability, Coach, Membership, Organization

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (same pattern as the rest of the test suite)
# ---------------------------------------------------------------------------

def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _make_coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _avail_url(org_id, athlete_id):
    return f"/api/p1/orgs/{org_id}/athletes/{athlete_id}/availability/"


SEVEN_DAYS = [
    {"day_of_week": i, "is_available": i < 5, "reason": "", "preferred_time": ""}
    for i in range(7)
]


# ==============================================================================
# Tests
# ==============================================================================

class AthleteAvailabilityBulkUpdateTests(TestCase):

    def setUp(self):
        self.client = APIClient()

        # Org A — primary
        self.org = _make_org("AvailOrgA")

        self.coach_user = _make_user("avail_coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        self.athlete_user = _make_user("avail_athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Org B — for cross-org test
        self.org_b = _make_org("AvailOrgB")
        self.coach_b_user = _make_user("avail_coach_b")
        _make_membership(self.coach_b_user, self.org_b, "coach")
        _make_coach(self.coach_b_user, self.org_b)

        self.url = _avail_url(self.org.id, self.athlete.id)

    # --- Happy path ---

    def test_put_replaces_all_records(self):
        """PUT with 7 items creates 7 records, replacing any existing ones."""
        # Seed 3 records to verify they are replaced, not appended.
        AthleteAvailability.objects.create(
            athlete=self.athlete, organization=self.org,
            day_of_week=0, is_available=True,
        )
        AthleteAvailability.objects.create(
            athlete=self.athlete, organization=self.org,
            day_of_week=1, is_available=True,
        )
        AthleteAvailability.objects.create(
            athlete=self.athlete, organization=self.org,
            day_of_week=2, is_available=True,
        )

        self.client.force_authenticate(user=self.athlete_user)
        resp = self.client.put(self.url, SEVEN_DAYS, format="json")

        self.assertEqual(resp.status_code, 200)
        qs = AthleteAvailability.objects.filter(
            athlete=self.athlete, organization=self.org
        )
        self.assertEqual(qs.count(), 7)

    def test_put_sets_is_available_correctly(self):
        """PUT reflects is_available values from the payload."""
        payload = [
            {"day_of_week": i, "is_available": i == 3, "reason": "", "preferred_time": ""}
            for i in range(7)
        ]
        self.client.force_authenticate(user=self.athlete_user)
        resp = self.client.put(self.url, payload, format="json")

        self.assertEqual(resp.status_code, 200)
        thursday = AthleteAvailability.objects.get(
            athlete=self.athlete, organization=self.org, day_of_week=3
        )
        self.assertTrue(thursday.is_available)
        monday = AthleteAvailability.objects.get(
            athlete=self.athlete, organization=self.org, day_of_week=0
        )
        self.assertFalse(monday.is_available)

    def test_put_empty_payload_clears_all_records(self):
        """PUT with empty list removes all existing records."""
        AthleteAvailability.objects.create(
            athlete=self.athlete, organization=self.org,
            day_of_week=0, is_available=True,
        )
        self.client.force_authenticate(user=self.athlete_user)
        resp = self.client.put(self.url, [], format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            AthleteAvailability.objects.filter(athlete=self.athlete).count(), 0
        )

    # --- Auth / tenancy gates ---

    def test_unauthenticated_rejected(self):
        """Unauthenticated PUT must be rejected (401)."""
        resp = self.client.put(self.url, SEVEN_DAYS, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_cross_org_actor_cannot_put(self):
        """Coach from org-B cannot PUT to org-A athlete's availability."""
        self.client.force_authenticate(user=self.coach_b_user)
        resp = self.client.put(self.url, SEVEN_DAYS, format="json")
        # resolve_membership raises PermissionDenied (403) for wrong org
        self.assertIn(resp.status_code, (403, 404))

    def test_coach_can_put(self):
        """Coach within the same org can also bulk-update athlete availability."""
        self.client.force_authenticate(user=self.coach_user)
        resp = self.client.put(self.url, SEVEN_DAYS, format="json")
        self.assertEqual(resp.status_code, 200)

    # --- Idempotency ---

    def test_put_twice_is_idempotent(self):
        """Two successive PUT calls produce the same result (no duplicates)."""
        self.client.force_authenticate(user=self.athlete_user)
        self.client.put(self.url, SEVEN_DAYS, format="json")
        resp = self.client.put(self.url, SEVEN_DAYS, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            AthleteAvailability.objects.filter(
                athlete=self.athlete, organization=self.org
            ).count(),
            7,
        )
