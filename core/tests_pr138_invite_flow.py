"""
PR-138 — Athlete invite flow tests.
Covers: InvitationDetailView (public GET) + InvitationAcceptView (authenticated POST).
"""
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    AthleteInvitation,
    CoachPricingPlan,
    Membership,
    Organization,
    OrgOAuthCredential,
)

User = get_user_model()

FAKE_MP_DATA = {
    "id": "preaproval_abc123",
    "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_plan_id=abc123",
    "status": "pending",
}


def _make_org(name="Test Org"):
    return Organization.objects.create(name=name)


def _make_user(email=None, password="pass1234"):
    email = email or f"user_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password=password)


def _make_plan(org, name="Base Plan", price_ars="5000.00", mp_plan_id="mp_plan_001"):
    return CoachPricingPlan.objects.create(
        organization=org,
        name=name,
        price_ars=price_ars,
        mp_plan_id=mp_plan_id,
        is_active=True,
    )


def _make_invitation(org, plan, email="athlete@test.com", days=30):
    return AthleteInvitation.objects.create(
        organization=org,
        coach_plan=plan,
        email=email,
        expires_at=timezone.now() + timedelta(days=days),
    )


def _make_mp_cred(org):
    return OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="mp_access_token",
        refresh_token="mp_refresh_token",
        provider_user_id="mp_user_123",
    )


class InvitationDetailViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.plan = _make_plan(self.org)
        self.invite = _make_invitation(self.org, self.plan)

    def _url(self, token=None):
        tok = token or self.invite.token
        return f"/api/billing/invitations/{tok}/"

    def test_valid_pending_returns_200_with_details(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["organization_name"], self.org.name)
        self.assertEqual(data["plan_name"], self.plan.name)
        self.assertEqual(data["currency"], "ARS")
        self.assertIn("price", data)
        self.assertIn("expires_at", data)
        # No sensitive fields
        self.assertNotIn("token", data)
        self.assertNotIn("email", data)
        self.assertNotIn("mp_preapproval_id", data)

    def test_nonexistent_token_returns_404(self):
        resp = self.client.get(f"/api/billing/invitations/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_expired_invitation_returns_200_status_expired(self):
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "expired")
        # DB should be updated to expired
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, AthleteInvitation.Status.EXPIRED)

    def test_already_accepted_returns_200_already_accepted(self):
        self.invite.status = AthleteInvitation.Status.ACCEPTED
        self.invite.save()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "already_accepted")


class InvitationAcceptViewTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.org = _make_org()
        self.plan = _make_plan(self.org)
        _make_mp_cred(self.org)
        self.athlete_user = _make_user("athlete@invite.com")
        self.invite = _make_invitation(self.org, self.plan, email="athlete@invite.com")

    def _url(self, token=None):
        tok = token or self.invite.token
        return f"/api/billing/invitations/{tok}/accept/"

    # ── auth guard ──────────────────────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        resp = self.api.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── valid acceptance ─────────────────────────────────────────────────────

    @patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value=FAKE_MP_DATA,
    )
    def test_valid_accept_creates_membership_and_marks_accepted(self, mock_mp):
        self.api.force_authenticate(user=self.athlete_user)
        resp = self.api.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("redirect_url", data)
        self.assertEqual(data["redirect_url"], FAKE_MP_DATA["init_point"])

        # Membership created
        self.assertTrue(
            Membership.objects.filter(
                user=self.athlete_user,
                organization=self.org,
                role="athlete",
            ).exists()
        )

        # Invitation marked accepted
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, AthleteInvitation.Status.ACCEPTED)
        self.assertEqual(self.invite.mp_preapproval_id, FAKE_MP_DATA["id"])

    # ── idempotent: second call returns already_member ───────────────────────

    @patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value=FAKE_MP_DATA,
    )
    def test_idempotent_second_call_returns_already_member(self, mock_mp):
        self.api.force_authenticate(user=self.athlete_user)
        # First call
        self.api.post(self._url())
        # Second call
        resp = self.api.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["redirect_url"], "/dashboard")
        self.assertTrue(data["already_member"])

    # ── expired invitation ───────────────────────────────────────────────────

    def test_expired_returns_400(self):
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()
        self.api.force_authenticate(user=self.athlete_user)
        resp = self.api.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()["error"], "invitation_expired")

    # ── nonexistent token ────────────────────────────────────────────────────

    def test_nonexistent_token_returns_404(self):
        self.api.force_authenticate(user=self.athlete_user)
        resp = self.api.post(f"/api/billing/invitations/{uuid.uuid4()}/accept/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
