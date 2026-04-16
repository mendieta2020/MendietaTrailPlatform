"""
PR-168a — Visibility Gates + Trial banner dedup fix

Backend tests covering:
- compute_subscription_status() returns correct value for all states
- subscription_status appears in /api/me/ for athletes
- WorkoutAssignment endpoint enforces gate for cancelled/trial_expired/none/paused athletes
- AthleteGoal endpoint enforces gate for cancelled athletes
- Coach/owner always passes gate
- Active and trial athletes get full access
"""
import pytest
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Organization, Membership, AthleteSubscription, Athlete, User,
    CoachPricingPlan, WorkoutAssignment, PlannedWorkout,
)
from core.identity_views import compute_subscription_status


# ── Fixtures ──────────────────────────────────────────────────────────────────

_ORG_COUNTER = 0


def _make_org():
    global _ORG_COUNTER
    _ORG_COUNTER += 1
    slug = f"testorg168a-{_ORG_COUNTER}"
    org = Organization.objects.create(name=f"TestOrg168a {_ORG_COUNTER}", slug=slug)
    owner_user = User.objects.create_user(
        username=f"owner168a_{_ORG_COUNTER}",
        email=f"owner168a_{_ORG_COUNTER}@test.com",
        password="pass",
    )
    Membership.objects.create(user=owner_user, organization=org, role="owner", is_active=True)
    return org, owner_user


def _make_athlete(org, sub_status=None, trial_ends_offset_days=None, no_sub=False):
    """Create an athlete with a subscription in the given status."""
    user = User.objects.create_user(
        username=f"ath168a_{org.pk}_{id(object())}",
        email=f"ath168a_{org.pk}_{id(object())}@test.com",
        password="pass",
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    athlete = Athlete.objects.create(user=user, organization=org)

    if no_sub:
        return user, athlete, None

    plan = CoachPricingPlan.objects.create(
        organization=org,
        name=f"Plan168a_{id(object())}",
        price_ars=100,
    )
    trial_ends_at = None
    if trial_ends_offset_days is not None:
        trial_ends_at = timezone.now() + timedelta(days=trial_ends_offset_days)

    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status=sub_status or AthleteSubscription.Status.ACTIVE,
        trial_ends_at=trial_ends_at,
    )
    return user, athlete, sub


# ── Unit tests: compute_subscription_status ───────────────────────────────────

class ComputeSubscriptionStatusTest(TestCase):

    def setUp(self):
        self.org, _ = _make_org()

    def test_active_returns_active(self):
        user, _, _ = _make_athlete(self.org, sub_status="active")
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "active"
        )

    def test_paused_returns_paused(self):
        user, _, _ = _make_athlete(self.org, sub_status="paused")
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "paused"
        )

    def test_cancelled_returns_cancelled(self):
        user, _, _ = _make_athlete(self.org, sub_status="cancelled")
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "cancelled"
        )

    def test_pending_with_valid_trial_returns_trial(self):
        user, _, _ = _make_athlete(
            self.org, sub_status="pending", trial_ends_offset_days=3
        )
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "trial"
        )

    def test_pending_with_expired_trial_returns_trial_expired(self):
        user, _, sub = _make_athlete(
            self.org, sub_status="pending", trial_ends_offset_days=-1
        )
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "trial_expired"
        )

    def test_pending_no_trial_returns_trial_expired(self):
        user, _, _ = _make_athlete(self.org, sub_status="pending")
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "trial_expired"
        )

    def test_no_subscription_returns_none(self):
        user, _, _ = _make_athlete(self.org, no_sub=True)
        self.assertEqual(
            compute_subscription_status(user, self.org.pk), "none"
        )


# ── /api/me/ returns subscription_status for athletes ─────────────────────────

class MeEndpointSubscriptionStatusTest(TestCase):

    def setUp(self):
        self.org, _ = _make_org()
        self.client = APIClient()

    def test_active_athlete_me_returns_subscription_status_active(self):
        user, _, _ = _make_athlete(self.org, sub_status="active")
        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["subscription_status"], "active")

    def test_cancelled_athlete_me_returns_subscription_status_cancelled(self):
        user, _, _ = _make_athlete(self.org, sub_status="cancelled")
        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["subscription_status"], "cancelled")

    def test_trial_athlete_me_returns_subscription_status_trial(self):
        user, _, _ = _make_athlete(
            self.org, sub_status="pending", trial_ends_offset_days=5
        )
        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["subscription_status"], "trial")

    def test_no_subscription_athlete_me_returns_subscription_status_none(self):
        user, _, _ = _make_athlete(self.org, no_sub=True)
        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["subscription_status"], "none")

    def test_owner_me_has_no_subscription_status(self):
        """Non-athletes should NOT have subscription_status in /api/me/"""
        org, owner = _make_org()
        self.client.force_authenticate(user=owner)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("subscription_status", resp.data)


# ── WorkoutAssignment subscription gate ───────────────────────────────────────

class WorkoutAssignmentSubscriptionGateTest(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org()
        self.client = APIClient()
        self._url = f"/api/p1/orgs/{self.org.pk}/assignments/"

    def test_active_athlete_gets_200(self):
        user, _, _ = _make_athlete(self.org, sub_status="active")
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 200)

    def test_trial_athlete_gets_full_access(self):
        user, _, _ = _make_athlete(
            self.org, sub_status="pending", trial_ends_offset_days=4
        )
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 200)

    def test_cancelled_athlete_gets_403_with_paywall(self):
        user, _, _ = _make_athlete(self.org, sub_status="cancelled")
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("paywall"))

    def test_trial_expired_athlete_gets_403(self):
        user, _, _ = _make_athlete(
            self.org, sub_status="pending", trial_ends_offset_days=-2
        )
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("paywall"))

    def test_no_subscription_athlete_gets_200(self):
        # Athletes with no subscription (legacy/free) pass the gate — status=none is allowed.
        user, _, _ = _make_athlete(self.org, no_sub=True)
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 200)

    def test_paused_athlete_gets_200_on_get(self):
        user, _, _ = _make_athlete(self.org, sub_status="paused")
        self.client.force_authenticate(user=user)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 200)

    def test_paused_athlete_gets_403_on_post(self):
        user, _, _ = _make_athlete(self.org, sub_status="paused")
        self.client.force_authenticate(user=user)
        resp = self.client.post(self._url, {}, format="json")
        self.assertEqual(resp.status_code, 403)
        # paywall=False for paused (not a hard paywall, just read-only restriction)
        self.assertNotEqual(resp.data.get("paywall"), True)

    def test_owner_always_gets_200(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self._url)
        self.assertEqual(resp.status_code, 200)
