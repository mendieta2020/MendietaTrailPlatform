"""
PR-151 — Launch Ready: /api/me org_name, Plan CRUD, Welcome Flow tests.
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
)

User = get_user_model()


def _make_org(name="Test Org"):
    slug = name.lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:4]}"
    return Organization.objects.create(name=name, slug=slug)


def _make_user(email=None):
    email = email or f"user_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password="TestPass123!")


class TestUserIdentityOrgName(TestCase):
    """Phase 1: /api/me returns org_name when membership exists."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org("Mendieta Trail")
        self.user = _make_user()

    def test_me_returns_org_name_for_owner(self):
        Membership.objects.create(user=self.user, organization=self.org, role="owner")
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["org_name"], "Mendieta Trail")
        self.assertEqual(resp.data["org_id"], self.org.pk)
        self.assertEqual(resp.data["role"], "owner")

    def test_me_returns_org_name_for_athlete(self):
        Membership.objects.create(user=self.user, organization=self.org, role="athlete")
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["org_name"], "Mendieta Trail")

    def test_me_no_membership(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/me")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("org_name", resp.data)


class TestPlanCRUD(TestCase):
    """Phase 2: Plan update and delete."""

    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        Membership.objects.create(user=self.user, organization=self.org, role="owner")
        self.plan = CoachPricingPlan.objects.create(
            organization=self.org, name="Classi", price_ars="38.00", is_active=True,
        )

    def test_update_plan_name(self):
        self.client.force_authenticate(self.user)
        resp = self.client.put(f"/api/billing/plans/{self.plan.pk}/", {
            "name": "Classic",
            "price_ars": "38000.00",
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Classic")
        self.assertEqual(resp.data["price_ars"], "38000.00")

    def test_delete_plan_deactivates(self):
        self.client.force_authenticate(self.user)
        resp = self.client.delete(f"/api/billing/plans/{self.plan.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["deactivated"])
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.is_active)

    def test_update_wrong_org_404(self):
        other_org = _make_org("Other")
        other_user = _make_user()
        Membership.objects.create(user=other_user, organization=other_org, role="owner")
        self.client.force_authenticate(other_user)
        resp = self.client.put(f"/api/billing/plans/{self.plan.pk}/", {"name": "Hack"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        resp = self.client.put(f"/api/billing/plans/{self.plan.pk}/", {"name": "X"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
