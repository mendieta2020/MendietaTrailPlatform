"""
PR-167c — Subscription lifecycle: Pause / Cancel / Reactivate + Retention survey
Tests cover:
- Athlete-initiated pause, cancel, reactivate
- Owner-initiated pause, cancel, reactivate
- Guard conditions (wrong status → 400)
- Notification creation
- Webhook STATUS_MAP "paused" → "paused" (not "overdue")
All MP API calls are mocked — never hit real endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from datetime import timedelta

from core.models import (
    Organization, Membership, AthleteSubscription, Athlete, User,
    CoachPricingPlan, InternalMessage,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_org_with_owner():
    org = Organization.objects.create(name="TestOrg167c")
    owner = User.objects.create_user(
        username=f"owner_{org.pk}",
        email=f"owner_{org.pk}@test.com",
        password="pass",
        first_name="Coach",
        last_name="Owner",
    )
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)
    return org, owner


def _make_athlete_with_sub(org, status=AthleteSubscription.Status.ACTIVE, mp_preapproval_id=None):
    user = User.objects.create_user(
        username=f"athlete_{org.pk}_{status}_{id(org)}",
        email=f"athlete_{org.pk}_{status}_{id(org)}@test.com",
        password="pass",
        first_name="Atleta",
        last_name="Test",
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    athlete = Athlete.objects.create(user=user, organization=org)
    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan Test", price_ars=100,
        mp_plan_id="mp_plan_test_167c" if mp_preapproval_id else None,
    )
    sub = AthleteSubscription.objects.create(
        athlete=athlete, organization=org, coach_plan=plan,
        status=status,
        mp_preapproval_id=mp_preapproval_id,
    )
    return user, athlete, sub


# ── Athlete pause ─────────────────────────────────────────────────────────────

class TestAthleteSubscriptionPause(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org_with_owner()
        self.client = APIClient()

    def test_athlete_pause_active_subscription(self):
        """Athlete pauses active subscription: status → paused, notification sent."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        with patch("integrations.mercadopago.subscriptions.pause_subscription") as mock_pause:
            resp = self.client.post("/api/athlete/subscription/pause/", {"reason": "vacation"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "paused")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")
        self.assertIsNotNone(sub.paused_at)

    def test_athlete_pause_with_reason(self):
        """pause_reason and pause_comment are saved."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/pause/", {
            "reason": "injury", "comment": "Tendinitis rodilla"
        })

        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.pause_reason, "injury")
        self.assertEqual(sub.pause_comment, "Tendinitis rodilla")

    def test_athlete_pause_sends_notification_to_owner(self):
        """Owner receives InternalMessage when athlete pauses."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        before = InternalMessage.objects.filter(
            organization=self.org, recipient=self.owner,
        ).count()

        resp = self.client.post("/api/athlete/subscription/pause/", {"reason": "time"})
        self.assertEqual(resp.status_code, 200)

        after = InternalMessage.objects.filter(
            organization=self.org, recipient=self.owner,
        ).count()
        self.assertEqual(after, before + 1)

    def test_cannot_pause_already_paused(self):
        """Pausing a paused sub returns 400."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PAUSED)
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/athlete/subscription/pause/", {"reason": "injury"})
        self.assertEqual(resp.status_code, 400)

    def test_cannot_pause_pending(self):
        """Pausing a pending sub returns 400 (must be active first)."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PENDING)
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/athlete/subscription/pause/", {"reason": "injury"})
        self.assertEqual(resp.status_code, 400)

    def test_athlete_pause_calls_mp_api_when_preapproval_exists(self):
        """MP pause_subscription is called when mp_preapproval_id is set."""
        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.ACTIVE, mp_preapproval_id="preapp_123"
        )
        from core.models import OrgOAuthCredential
        OrgOAuthCredential.objects.create(
            organization=self.org, provider="mercadopago",
            access_token="tok_test", refresh_token="",
        )
        self.client.force_authenticate(user=user)

        with patch("integrations.mercadopago.subscriptions.pause_subscription") as mock_pause:
            mock_pause.return_value = {"status": "paused"}
            resp = self.client.post("/api/athlete/subscription/pause/", {"reason": "vacation"})

        self.assertEqual(resp.status_code, 200)
        mock_pause.assert_called_once_with("tok_test", "preapp_123")


# ── Athlete cancel ────────────────────────────────────────────────────────────

class TestAthleteSubscriptionCancel(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org_with_owner()
        self.client = APIClient()

    def test_athlete_cancel_active_subscription(self):
        """Athlete cancels active sub: status → cancelled, notification sent."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/cancel/", {"reason": "price"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "cancelled")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")
        self.assertIsNotNone(sub.cancelled_at)

    def test_athlete_cancel_paused_subscription(self):
        """Athlete can cancel from paused state."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PAUSED)
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/cancel/", {"reason": "not_using"})
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")
        # paused_at cleared on cancel
        self.assertIsNone(sub.paused_at)

    def test_athlete_cancel_with_survey(self):
        """cancellation_reason and comment are saved."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/cancel/", {
            "reason": "other", "comment": "Me fui a vivir afuera"
        })
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.cancellation_reason, "other")
        self.assertEqual(sub.cancellation_comment, "Me fui a vivir afuera")

    def test_athlete_cancel_sends_notification_to_owner(self):
        """Owner receives InternalMessage when athlete cancels."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)

        before = InternalMessage.objects.filter(organization=self.org, recipient=self.owner).count()
        self.client.post("/api/athlete/subscription/cancel/", {"reason": "price"})
        after = InternalMessage.objects.filter(organization=self.org, recipient=self.owner).count()
        self.assertEqual(after, before + 1)

    def test_cannot_cancel_already_cancelled(self):
        """Cancelling an already-cancelled sub returns 400."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.CANCELLED)
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/athlete/subscription/cancel/", {"reason": "price"})
        self.assertEqual(resp.status_code, 400)

    def test_athlete_cancel_calls_mp_api_when_preapproval_exists(self):
        """MP cancel_athlete_subscription is called when mp_preapproval_id is set."""
        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.ACTIVE, mp_preapproval_id="preapp_456"
        )
        from core.models import OrgOAuthCredential
        OrgOAuthCredential.objects.create(
            organization=self.org, provider="mercadopago",
            access_token="tok_test2", refresh_token="",
        )
        self.client.force_authenticate(user=user)

        with patch("integrations.mercadopago.subscriptions.cancel_athlete_subscription") as mock_cancel:
            mock_cancel.return_value = {"status": "cancelled"}
            resp = self.client.post("/api/athlete/subscription/cancel/", {"reason": "price"})

        self.assertEqual(resp.status_code, 200)
        mock_cancel.assert_called_once_with("tok_test2", "preapp_456")


# ── Athlete reactivate ────────────────────────────────────────────────────────

class TestAthleteSubscriptionReactivate(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org_with_owner()
        self.client = APIClient()

    def test_athlete_reactivate_paused(self):
        """Reactivating a paused sub (no MP preapproval) → status active."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PAUSED)
        sub.paused_at = timezone.now()
        sub.pause_reason = "vacation"
        sub.save()
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/reactivate/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "active")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")
        self.assertIsNone(sub.paused_at)
        self.assertIsNone(sub.pause_reason)

    def test_athlete_reactivate_paused_calls_mp(self):
        """Reactivating a paused sub with MP preapproval calls reactivate_subscription."""
        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.PAUSED, mp_preapproval_id="preapp_789"
        )
        from core.models import OrgOAuthCredential
        OrgOAuthCredential.objects.create(
            organization=self.org, provider="mercadopago",
            access_token="tok_test3", refresh_token="",
        )
        self.client.force_authenticate(user=user)

        with patch("integrations.mercadopago.subscriptions.reactivate_subscription") as mock_react:
            mock_react.return_value = {"status": "authorized"}
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "active")
        mock_react.assert_called_once_with("tok_test3", "preapp_789")

    def test_athlete_reactivate_cancelled_returns_redirect_url(self):
        """Reactivating a cancelled sub generates new payment link via plan init_point."""
        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.CANCELLED
        )
        # Give plan an mp_plan_id
        sub.coach_plan.mp_plan_id = "mp_plan_test_167c"
        sub.coach_plan.save()
        from core.models import OrgOAuthCredential
        OrgOAuthCredential.objects.create(
            organization=self.org, provider="mercadopago",
            access_token="tok_test4", refresh_token="",
        )
        self.client.force_authenticate(user=user)

        # FIX-1: creates individual preapproval; id stamped to DB before redirect
        with patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval") as mock_create:
            mock_create.return_value = {"id": "new_preapproval_167c", "init_point": "https://mp.com/checkout/new"}
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "pending")
        self.assertIn("redirect_url", resp.data)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "pending")
        # FIX-1: preapproval_id is now stamped (not None) so webhook fast-path works
        self.assertEqual(sub.mp_preapproval_id, "new_preapproval_167c")

    def test_cannot_reactivate_active(self):
        """Reactivating an already-active sub returns 400."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/athlete/subscription/reactivate/")
        self.assertEqual(resp.status_code, 400)


# ── Owner actions ─────────────────────────────────────────────────────────────

class TestOwnerSubscriptionAction(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org_with_owner()
        self.client = APIClient()

    def _url(self, sub_id):
        return f"/api/billing/athlete-subscriptions/{sub_id}/owner-action/"

    def test_owner_pause_subscription(self):
        """Owner can pause an active sub; athlete notified."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=self.owner)

        resp = self.client.post(self._url(sub.id), {"action": "pause", "reason": "owner_decision"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "paused")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")

        # Athlete receives notification
        notif = InternalMessage.objects.filter(
            organization=self.org, recipient=user, alert_type="subscription_paused"
        ).first()
        self.assertIsNotNone(notif)

    def test_owner_cancel_subscription(self):
        """Owner can cancel an active sub; athlete notified."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=self.owner)

        resp = self.client.post(self._url(sub.id), {"action": "cancel", "reason": "owner_decision"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "cancelled")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")

        notif = InternalMessage.objects.filter(
            organization=self.org, recipient=user, alert_type="subscription_cancelled"
        ).first()
        self.assertIsNotNone(notif)

    def test_owner_reactivate_paused_subscription(self):
        """Owner can reactivate a paused sub; athlete notified."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PAUSED)
        self.client.force_authenticate(user=self.owner)

        resp = self.client.post(self._url(sub.id), {"action": "reactivate"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "active")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

        notif = InternalMessage.objects.filter(
            organization=self.org, recipient=user, alert_type="subscription_reactivated"
        ).first()
        self.assertIsNotNone(notif)

    def test_owner_reactivate_cancelled_sets_pending(self):
        """Owner reactivating a cancelled sub → status pending."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.CANCELLED)
        self.client.force_authenticate(user=self.owner)

        resp = self.client.post(self._url(sub.id), {"action": "reactivate"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "pending")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "pending")

    def test_owner_cannot_pause_already_paused(self):
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.PAUSED)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self._url(sub.id), {"action": "pause"})
        self.assertEqual(resp.status_code, 400)

    def test_owner_invalid_action_returns_400(self):
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self._url(sub.id), {"action": "teleport"})
        self.assertEqual(resp.status_code, 400)

    def test_non_owner_cannot_use_owner_action(self):
        """Athlete cannot use owner-action endpoint."""
        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=user)
        resp = self.client.post(self._url(sub.id), {"action": "pause"})
        self.assertIn(resp.status_code, [403, 404])

    def test_cross_org_subscription_not_accessible(self):
        """Owner from org A cannot touch sub from org B."""
        import uuid as _uuid
        org2 = Organization.objects.create(name="OtherOrg", slug=_uuid.uuid4().hex[:12])
        owner2 = User.objects.create_user(username="owner_b_167c", email="owner_b@test.com", password="pass")
        Membership.objects.create(user=owner2, organization=org2, role="owner", is_active=True)

        user, athlete, sub = _make_athlete_with_sub(self.org, AthleteSubscription.Status.ACTIVE)
        self.client.force_authenticate(user=owner2)
        resp = self.client.post(self._url(sub.id), {"action": "cancel"})
        self.assertIn(resp.status_code, [403, 404])


# ── Webhook STATUS_MAP ────────────────────────────────────────────────────────

class TestWebhookPausedStatusMap(TestCase):

    def setUp(self):
        self.org, self.owner = _make_org_with_owner()

    def test_webhook_paused_maps_to_paused_not_overdue(self):
        """Webhook 'paused' event → sub.status = 'paused' (not 'overdue')."""
        from integrations.mercadopago.athlete_webhook import _apply_status_transition

        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.ACTIVE, mp_preapproval_id="preapp_webhook_test"
        )

        result = _apply_status_transition(sub, "paused", "preapp_webhook_test")
        self.assertEqual(result, "updated")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")

    def test_webhook_authorized_maps_to_active(self):
        """Webhook 'authorized' → still maps to 'active'."""
        from integrations.mercadopago.athlete_webhook import _apply_status_transition

        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.PENDING, mp_preapproval_id="preapp_wh2"
        )

        result = _apply_status_transition(sub, "authorized", "preapp_wh2")
        self.assertEqual(result, "updated")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

    def test_webhook_cancelled_maps_to_cancelled(self):
        """Webhook 'cancelled' → still maps to 'cancelled'."""
        from integrations.mercadopago.athlete_webhook import _apply_status_transition

        user, athlete, sub = _make_athlete_with_sub(
            self.org, AthleteSubscription.Status.ACTIVE, mp_preapproval_id="preapp_wh3"
        )

        result = _apply_status_transition(sub, "cancelled", "preapp_wh3")
        self.assertEqual(result, "updated")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")

    def test_status_map_paused_key(self):
        """Direct check: STATUS_MAP['paused'] == 'paused'."""
        from integrations.mercadopago.athlete_webhook import STATUS_MAP
        self.assertEqual(STATUS_MAP["paused"], "paused")
        self.assertNotEqual(STATUS_MAP["paused"], "overdue")
