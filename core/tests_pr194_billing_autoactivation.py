"""
PR-194 — Auto-activation fix + overdue gate + churn data.

T1: Cancel → resubscribe → mp_preapproval_id is NEW id in DB BEFORE athlete
    reaches MP checkout (FIX-1).
T2: Cancel → resubscribe → MP webhook arrives → status = active WITHOUT sync
    (FIX-1 end-to-end via fast path).
T3: Overdue → reactivate → returns MP checkout URL, status=pending (FIX-3).
T4: Already active → reactivate → 400 (FIX-3 guard unchanged for active).
T5: pause_reason saved to DB after pause flow (FIX-6 verify).
T6: cancellation_reason saved to DB after cancel flow (FIX-6 verify).
T7: Strategy-4 matches cancelled sub with null preapproval_id (FIX-2).
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── shared helpers ────────────────────────────────────────────────────────────

def _make_org_plan_cred(suffix):
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username=f"owner_{suffix}", email=f"owner_{suffix}@test.com", password="pw",
    )
    org = Organization.objects.create(name=f"Org{suffix}", slug=f"org-{suffix}")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)
    plan = CoachPricingPlan.objects.create(
        organization=org, name=f"Plan{suffix}", price_ars=8000,
        mp_plan_id=f"mp_plan_{suffix}", is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token=f"tok_{suffix}",
    )
    return owner, org, plan


def _make_athlete_sub(org, plan, email_suffix, status="active", mp_preapproval_id=None):
    from core.models import Membership, Athlete, AthleteSubscription

    user = User.objects.create_user(
        username=f"ath_{email_suffix}", email=f"ath_{email_suffix}@test.com", password="pw",
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    ath = Athlete.objects.create(user=user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=ath, organization=org, coach_plan=plan,
        status=status, mp_preapproval_id=mp_preapproval_id,
    )
    return user, ath, sub


class _FakeCred:
    def __init__(self, org):
        self.organization = org
        self.organization_id = org.pk
        self.access_token = "tok_fake"


# ── T1: stamp preapproval_id BEFORE returning init_point (FIX-1) ─────────────

@pytest.mark.django_db
def test_reactivate_cancelled_stamps_preapproval_before_redirect():
    """
    FIX-1: After cancel + reactivate, mp_preapproval_id is set in DB
    before the view returns the redirect_url to the frontend.
    """
    _, org, plan = _make_org_plan_cred("194t1")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t1", status="cancelled", mp_preapproval_id="old_cancelled_id",
    )

    client = APIClient()
    client.force_authenticate(user=athlete_user)

    fake_preapproval = {"id": "NEW_PREAPPROVAL_194", "init_point": "https://mp.com/checkout/NEW_194"}

    with patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value=fake_preapproval,
    ):
        resp = client.post("/api/athlete/subscription/reactivate/")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "redirect_url" in data
    assert "NEW_194" in data["redirect_url"]

    sub.refresh_from_db()
    # FIX-1 invariant: ID stamped before redirect
    assert sub.mp_preapproval_id == "NEW_PREAPPROVAL_194"
    assert sub.status == "pending"


# ── T2: webhook fast-path activates after stamp (FIX-1 end-to-end) ───────────

@pytest.mark.django_db
def test_reactivate_cancelled_webhook_activates_without_manual_sync():
    """
    FIX-1: After stamp, the webhook fast-path matches the sub by preapproval_id
    and activates it — no manual /sync call required.
    """
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    _, org, plan = _make_org_plan_cred("194t2")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t2", status="cancelled", mp_preapproval_id=None,
    )

    # Simulate Fix-1: stamp new preapproval_id before athlete pays
    sub.mp_preapproval_id = "STAMPED_194t2"
    sub.status = "pending"
    sub.save(update_fields=["mp_preapproval_id", "status"])

    # Webhook arrives with the stamped ID
    payload = {"id": "STAMPED_194t2", "status": "authorized"}
    result = process_athlete_subscription_webhook(payload)

    assert result["outcome"] == "updated"
    sub.refresh_from_db()
    assert sub.status == "active"


# ── T3: overdue → reactivate requires payment (FIX-3) ────────────────────────

@pytest.mark.django_db
def test_reactivate_overdue_returns_checkout_url():
    """
    FIX-3: Overdue athlete cannot self-reactivate without payment.
    Reactivate endpoint creates new preapproval and returns redirect_url.
    """
    _, org, plan = _make_org_plan_cred("194t3")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t3", status="overdue", mp_preapproval_id="overdue_preapp",
    )

    client = APIClient()
    client.force_authenticate(user=athlete_user)

    fake_preapproval = {"id": "NEW_OVERDUE_194", "init_point": "https://mp.com/checkout/OVERDUE_194"}

    with patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value=fake_preapproval,
    ):
        resp = client.post("/api/athlete/subscription/reactivate/")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "redirect_url" in data

    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "NEW_OVERDUE_194"
    assert sub.status == "pending"


# ── T4: active → reactivate → 400 (guard correct for active) ─────────────────

@pytest.mark.django_db
def test_reactivate_active_returns_400():
    """
    Already-active subscription → reactivate returns 400.
    FIX-4 (frontend) relies on this contract.
    """
    _, org, plan = _make_org_plan_cred("194t4")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t4", status="active", mp_preapproval_id="active_preapp",
    )

    client = APIClient()
    client.force_authenticate(user=athlete_user)
    resp = client.post("/api/athlete/subscription/reactivate/")
    assert resp.status_code == 400


# ── T5: pause_reason saved to DB (FIX-6 verify) ──────────────────────────────

@pytest.mark.django_db
def test_pause_reason_saved_to_db():
    """
    FIX-6: pause_reason and pause_comment are written to AthleteSubscription.
    """
    _, org, plan = _make_org_plan_cred("194t5")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t5", status="active", mp_preapproval_id=None,
    )

    client = APIClient()
    client.force_authenticate(user=athlete_user)
    resp = client.post(
        "/api/athlete/subscription/pause/",
        {"reason": "Estoy lesionado/a", "comment": "Rodilla"},
        format="json",
    )
    assert resp.status_code == 200

    sub.refresh_from_db()
    assert sub.status == "paused"
    assert sub.pause_reason == "Estoy lesionado/a"
    assert sub.pause_comment == "Rodilla"


# ── T6: cancellation_reason saved to DB (FIX-6 verify) ───────────────────────

@pytest.mark.django_db
def test_cancellation_reason_saved_to_db():
    """
    FIX-6: cancellation_reason and cancellation_comment are written to AthleteSubscription.
    """
    _, org, plan = _make_org_plan_cred("194t6")
    athlete_user, ath, sub = _make_athlete_sub(
        org, plan, "194t6", status="active", mp_preapproval_id=None,
    )

    client = APIClient()
    client.force_authenticate(user=athlete_user)
    resp = client.post(
        "/api/athlete/subscription/cancel/",
        {"reason": "Razones económicas", "comment": "Ajuste de presupuesto"},
        format="json",
    )
    assert resp.status_code == 200

    sub.refresh_from_db()
    assert sub.status == "cancelled"
    assert sub.cancellation_reason == "Razones económicas"
    assert sub.cancellation_comment == "Ajuste de presupuesto"


# ── T7: Strategy-4 matches cancelled sub (FIX-2) ─────────────────────────────

@pytest.mark.django_db
def test_reconcile_strategy4_matches_cancelled_sub():
    """
    FIX-2: Strategy 4 extended to match cancelled subs with null preapproval_id.
    Race condition: webhook arrives after mp_preapproval_id cleared but before
    new ID stamped → sub has status='cancelled', mp_preapproval_id=None.
    """
    from integrations.mercadopago.athlete_webhook import _reconcile_by_payer

    _, org, plan = _make_org_plan_cred("194t7")
    _, ath, sub = _make_athlete_sub(
        org, plan, "194t7",
        status="cancelled",
        mp_preapproval_id=None,  # cleared during reactivation flow
    )

    mp_data = {
        "id": "RACE_CONDITION_ID",
        "payer_id": "",
        "payer_email": "",
        "preapproval_plan_id": f"mp_plan_194t7",
        "status": "authorized",
    }

    result = _reconcile_by_payer(mp_data, _FakeCred(org))

    assert result is not None
    assert result.pk == sub.pk
    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "RACE_CONDITION_ID"
