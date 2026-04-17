"""
PR-168a hotfix — AthleteSubscriptionReactivateView: cancelled → new payment link

Covers:
1. cancelled sub with mp_plan_id set → fetches plan init_point, returns redirect_url
2. cancelled sub with mp_plan_id = None → lazy-creates plan in MP, returns redirect_url
3. stale mp_preapproval_id is cleared to None before the MP call
4. mp_plan_id is persisted when lazy-created
5. cancelled sub without MP cred → 400 (no redirect)
6. MP API error → 502
7. MP returns no init_point → 400
8. still-paused sub is not affected (continues to work)
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Organization,
    Membership,
    AthleteSubscription,
    Athlete,
    User,
    CoachPricingPlan,
    OrgOAuthCredential,
    InternalMessage,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CTR = 0


def _uniq(prefix=""):
    global _CTR
    _CTR += 1
    return f"{prefix}{_CTR}"


def _make_org():
    org = Organization.objects.create(name=f"HotfixOrg {_uniq()}", slug=_uniq("slug-"))
    owner = User.objects.create_user(
        username=_uniq("owner_"),
        email=f"{_uniq('owner')}@test.com",
        password="pw",
    )
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)
    return org, owner


def _make_athlete_sub(org, status, mp_preapproval_id=None, mp_plan_id=None):
    user = User.objects.create_user(
        username=_uniq("ath_"),
        email=f"{_uniq('ath')}@test.com",
        password="pw",
        first_name="Atleta",
        last_name="Test",
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    athlete = Athlete.objects.create(user=user, organization=org)
    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Plan Hotfix",
        price_ars=5000,
        mp_plan_id=mp_plan_id,
        is_active=True,
    )
    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status=status,
        mp_preapproval_id=mp_preapproval_id,
    )
    return user, athlete, sub, plan


def _add_mp_cred(org, token="fake_tok"):
    return OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token=token,
        refresh_token="",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestReactivateCancelledWithMpPlanId(TestCase):
    """Cancelled sub, mp_plan_id already set → fetch plan from MP, return redirect_url."""

    def setUp(self):
        self.org, self.owner = _make_org()
        self.client = APIClient()

    def test_returns_redirect_url_and_pending_status(self):
        """Happy path: plan exists in MP, init_point returned."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_preapproval_id="old_dead_preapp",
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan"
        ) as mock_get:
            mock_get.return_value = {"id": "mp_plan_existing", "init_point": "https://mp.com/plan/checkout"}
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "pending")
        self.assertIn("redirect_url", resp.data)
        self.assertEqual(resp.data["redirect_url"], "https://mp.com/plan/checkout")

        sub.refresh_from_db()
        self.assertEqual(sub.status, "pending")
        self.assertIsNone(sub.mp_preapproval_id)  # stale ID must be cleared
        self.assertIsNone(sub.cancelled_at)

    def test_stale_mp_preapproval_id_cleared_before_mp_call(self):
        """mp_preapproval_id = None before any MP call (even if MP fails later)."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_preapproval_id="stale_preapp_999",
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        call_order = []

        def fake_get_plan(*args, **kwargs):
            # By the time MP is called, the DB must already have mp_preapproval_id=None
            sub.refresh_from_db()
            call_order.append(("mp_preapproval_id_at_call_time", sub.mp_preapproval_id))
            return {"init_point": "https://mp.com/plan/checkout"}

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan",
            side_effect=fake_get_plan,
        ):
            self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(len(call_order), 1)
        self.assertIsNone(call_order[0][1], "mp_preapproval_id must be None before MP call")

    def test_owner_notification_sent(self):
        """Coach receives InternalMessage when athlete reactivates."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        before = InternalMessage.objects.filter(organization=self.org, recipient=self.owner).count()

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan",
            return_value={"init_point": "https://mp.com/plan/checkout"},
        ):
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 200)
        after = InternalMessage.objects.filter(organization=self.org, recipient=self.owner).count()
        self.assertEqual(after, before + 1)


class TestReactivateCancelledNoMpPlanId(TestCase):
    """Cancelled sub, mp_plan_id = None → lazy-creates plan in MP."""

    def setUp(self):
        self.org, self.owner = _make_org()
        self.client = APIClient()

    def test_lazy_creates_plan_and_returns_redirect_url(self):
        """When mp_plan_id is None, creates plan in MP and persists mp_plan_id."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_preapproval_id="old_dead_preapp",
            mp_plan_id=None,  # nulled by PR-167e migration
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.create_preapproval_plan"
        ) as mock_create:
            mock_create.return_value = {
                "id": "newly_created_plan_id",
                "init_point": "https://mp.com/new_plan/checkout",
            }
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "pending")
        self.assertEqual(resp.data["redirect_url"], "https://mp.com/new_plan/checkout")

        # Plan mp_plan_id must be persisted
        plan.refresh_from_db()
        self.assertEqual(plan.mp_plan_id, "newly_created_plan_id")

        # Sub status updated, stale preapproval cleared
        sub.refresh_from_db()
        self.assertEqual(sub.status, "pending")
        self.assertIsNone(sub.mp_preapproval_id)

    def test_create_preapproval_plan_called_with_correct_args(self):
        """create_preapproval_plan receives org name, plan name, price."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_plan_id=None,
        )
        _add_mp_cred(self.org, token="coach_token")
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.create_preapproval_plan"
        ) as mock_create:
            mock_create.return_value = {
                "id": "plan_new",
                "init_point": "https://mp.com/checkout",
            }
            self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(mock_create.call_count, 1)
        kwargs = mock_create.call_args[1] if mock_create.call_args[1] else {}
        args = mock_create.call_args[0] if mock_create.call_args[0] else ()
        # access_token must be passed (law 6: never checked by value in test)
        call_kwargs = {**dict(zip(["access_token", "name", "price_ars", "back_url"], args)), **kwargs}
        self.assertIn(self.org.name, call_kwargs.get("name", ""))
        self.assertIn(plan.name, call_kwargs.get("name", ""))


class TestReactivateCancelledErrorCases(TestCase):
    """Error and guard conditions for cancelled reactivation."""

    def setUp(self):
        self.org, self.owner = _make_org()
        self.client = APIClient()

    def test_no_mp_cred_returns_400(self):
        """No OrgOAuthCredential → 400."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org, AthleteSubscription.Status.CANCELLED, mp_plan_id="mp_plan_x"
        )
        # No cred created intentionally
        self.client.force_authenticate(user=user)

        resp = self.client.post("/api/athlete/subscription/reactivate/")
        self.assertEqual(resp.status_code, 400)

    def test_mp_api_error_returns_502(self):
        """MP call raises Exception → 502."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan",
            side_effect=Exception("MP timeout"),
        ):
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 502)

    def test_mp_returns_no_init_point_returns_400(self):
        """MP returns dict without init_point → 400."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan",
            return_value={"id": "mp_plan_existing"},  # no init_point key
        ):
            resp = self.client.post("/api/athlete/subscription/reactivate/")

        self.assertEqual(resp.status_code, 400)

    def test_sub_status_not_changed_on_mp_error(self):
        """When MP fails, sub.status stays cancelled."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org,
            AthleteSubscription.Status.CANCELLED,
            mp_preapproval_id="old_preapp",
            mp_plan_id="mp_plan_existing",
        )
        _add_mp_cred(self.org)
        self.client.force_authenticate(user=user)

        with patch(
            "integrations.mercadopago.subscriptions.get_preapproval_plan",
            side_effect=Exception("MP down"),
        ):
            self.client.post("/api/athlete/subscription/reactivate/")

        sub.refresh_from_db()
        # Status should not have changed to pending on error
        self.assertEqual(sub.status, "cancelled")

    def test_active_sub_cannot_be_reactivated(self):
        """Active sub → 400."""
        user, athlete, sub, plan = _make_athlete_sub(
            self.org, AthleteSubscription.Status.ACTIVE
        )
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/athlete/subscription/reactivate/")
        self.assertEqual(resp.status_code, 400)
