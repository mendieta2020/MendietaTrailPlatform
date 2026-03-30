"""
PR-150 — BillingOrgMixin, MP Connect, Universal Invite Link, Athlete Subscription tests.
"""

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    CoachPricingPlan,
    Membership,
    Organization,
    OrganizationInviteLink,
    OrgOAuthCredential,
)

User = get_user_model()


def _make_org(name="Test Org"):
    slug = name.lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:4]}"
    return Organization.objects.create(name=name, slug=slug)


def _make_user(email=None, password="TestPass123!"):
    email = email or f"user_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password=password)


def _make_plan(org, name="Classic", price_ars="38000.00"):
    return CoachPricingPlan.objects.create(
        organization=org, name=name, price_ars=price_ars, is_active=True,
    )


class TestBillingOrgResolution(TestCase):
    """Phase 0: BillingOrgMixin resolves org from Membership."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        Membership.objects.create(
            user=self.user, organization=self.org, role="owner",
        )

    def test_billing_status_resolves_org(self):
        """BillingStatusView should work when auth_organization is resolved from Membership."""
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/billing/status/")
        # Should NOT return 403 anymore — org resolved from Membership
        self.assertIn(resp.status_code, [200, 404])

    def test_plans_list_resolves_org(self):
        """CoachPricingPlanListCreateView should resolve org from Membership."""
        self.client.force_authenticate(self.user)
        _make_plan(self.org)
        resp = self.client.get("/api/billing/plans/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_plans_create_resolves_org(self):
        """Creating a plan should work with org from Membership."""
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/billing/plans/", {
            "name": "Test Plan",
            "price_ars": "25000",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_no_membership_returns_403(self):
        """User without Membership gets 403."""
        user_no_org = _make_user(email="noorg@test.com")
        self.client.force_authenticate(user_no_org)
        resp = self.client.get("/api/billing/plans/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TestInviteLinkView(TestCase):
    """Phase 2: Universal invite link CRUD."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org("Mendieta Trail")
        self.user = _make_user()
        Membership.objects.create(
            user=self.user, organization=self.org, role="owner",
        )

    def test_get_creates_link(self):
        """GET /api/billing/invite-link/ creates link if none exists."""
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/billing/invite-link/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("slug", resp.data)
        self.assertIn("url", resp.data)
        self.assertTrue(resp.data["is_active"])

    def test_get_returns_existing_link(self):
        """GET returns the same link on second call."""
        self.client.force_authenticate(self.user)
        resp1 = self.client.get("/api/billing/invite-link/")
        resp2 = self.client.get("/api/billing/invite-link/")
        self.assertEqual(resp1.data["slug"], resp2.data["slug"])

    def test_regenerate_changes_slug(self):
        """POST /api/billing/invite-link/regenerate/ changes the slug."""
        self.client.force_authenticate(self.user)
        resp1 = self.client.get("/api/billing/invite-link/")
        old_slug = resp1.data["slug"]
        resp2 = self.client.post("/api/billing/invite-link/regenerate/")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp2.data["slug"], old_slug)

    def test_unauthenticated_returns_401(self):
        resp = self.client.get("/api/billing/invite-link/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestJoinDetailView(TestCase):
    """Phase 2: Public join page endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org("Trail Team")
        _make_plan(self.org, "Classic", "38000")
        _make_plan(self.org, "Ultra", "60000")
        self.link = OrganizationInviteLink.objects.create(
            organization=self.org, slug="test-join-link",
        )

    def test_join_returns_org_and_plans(self):
        """Public GET returns org name + active plans."""
        resp = self.client.get("/api/billing/join/test-join-link/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["organization_name"], "Trail Team")
        self.assertEqual(len(resp.data["plans"]), 2)
        self.assertEqual(resp.data["currency"], "ARS")

    def test_join_invalid_slug(self):
        resp = self.client.get("/api/billing/join/nonexistent/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_join_inactive_link(self):
        self.link.is_active = False
        self.link.save()
        resp = self.client.get("/api/billing/join/test-join-link/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TestAthleteMySubscription(TestCase):
    """Phase 3: Athlete sees own subscription."""

    def setUp(self):
        self.client = APIClient()
        self.user = _make_user()

    def test_no_subscription(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/athlete/subscription/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["has_subscription"])

    def test_unauthenticated(self):
        resp = self.client.get("/api/athlete/subscription/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestMPConnectStatus(TestCase):
    """Phase 1: MP connection status in billing."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        Membership.objects.create(
            user=self.user, organization=self.org, role="owner",
        )

    def test_billing_status_shows_mp_not_connected(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/billing/status/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data.get("mp_connected", True))

    def test_billing_status_shows_mp_connected(self):
        OrgOAuthCredential.objects.create(
            organization=self.org, provider="mercadopago",
            access_token="test", provider_user_id="123",
        )
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/billing/status/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["mp_connected"])
