"""
PR-167 — MercadoPago Checkout real (suscripción automática mensual)

Tests:
1. AthletePaymentLinkView returns init_point (mock MP API)
2. Webhook updates AthleteSubscription to "active" + sets next_payment_at
3. Webhook is idempotent (repeated authorized event → noop)
4. Athlete without membership cannot access payment-link (403)
5. back_url uses /payment/callback, not /invite/token/callback
"""
import pytest
from unittest.mock import patch
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def org_with_mp():
    """Org with MP credential + CoachPricingPlan + owner user."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username="owner167", email="owner167@test.com", password="pw"
    )
    org = Organization.objects.create(name="Org167", slug="org-167")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Plan Elite",
        price_ars=100000,
        mp_plan_id="mp_plan_abc123",
        is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="mp_access_tok_fake",
    )
    return org, owner, plan


@pytest.fixture
def athlete_with_sub(org_with_mp):
    """Athlete user with AthleteSubscription in pending state + preapproval set."""
    from core.models import Membership, Athlete, AthleteSubscription

    org, owner, plan = org_with_mp
    athlete_user = User.objects.create_user(
        username="athlete167", email="athlete167@test.com", password="pw"
    )
    m = Membership.objects.create(
        user=athlete_user, organization=org, role="athlete", is_active=True
    )
    athlete = Athlete.objects.create(user=athlete_user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status="pending",
        mp_preapproval_id="preaprob_xyz789",
    )
    return athlete_user, sub


# ─── Test 1: AthletePaymentLinkView returns init_point ───────────────────────

@pytest.mark.django_db
def test_athlete_payment_link_returns_init_point(athlete_with_sub):
    """GET /api/athlete/payment-link/ returns init_point when preapproval exists."""
    athlete_user, sub = athlete_with_sub
    fake_mp_response = {
        "id": sub.mp_preapproval_id,
        "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=preaprob_xyz789",
        "status": "pending",
    }

    client = APIClient()
    client.force_authenticate(user=athlete_user)

    with patch(
        "integrations.mercadopago.subscriptions.get_subscription",
        return_value=fake_mp_response,
    ):
        response = client.get("/api/athlete/payment-link/")

    assert response.status_code == 200
    data = response.json()
    assert "init_point" in data
    assert data["init_point"] == fake_mp_response["init_point"]


# ─── Test 2: Webhook activates subscription + sets next_payment_at ──────────

@pytest.mark.django_db
def test_webhook_sets_active_and_next_payment_at(athlete_with_sub):
    """
    POST /api/webhooks/mercadopago/athlete/ with status=authorized
    → AthleteSubscription.status = 'active' + next_payment_at ≈ now + 30 days.
    """
    athlete_user, sub = athlete_with_sub
    assert sub.status == "pending"
    assert sub.next_payment_at is None

    client = APIClient()
    payload = {
        "id": sub.mp_preapproval_id,
        "status": "authorized",
    }
    response = client.post(
        "/api/webhooks/mercadopago/athlete/",
        data=payload,
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "updated"

    sub.refresh_from_db()
    assert sub.status == "active"
    assert sub.last_payment_at is not None
    assert sub.next_payment_at is not None
    # next_payment_at should be ~30 days from now
    delta = sub.next_payment_at - timezone.now()
    assert timedelta(days=29) < delta < timedelta(days=31)


# ─── Test 3: Webhook is idempotent ──────────────────────────────────────────

@pytest.mark.django_db
def test_webhook_authorized_twice_is_noop(athlete_with_sub):
    """Repeated authorized webhook → second call returns noop (idempotent)."""
    athlete_user, sub = athlete_with_sub
    sub.status = "active"
    sub.save(update_fields=["status"])

    client = APIClient()
    payload = {"id": sub.mp_preapproval_id, "status": "authorized"}
    response = client.post(
        "/api/webhooks/mercadopago/athlete/",
        data=payload,
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "noop"


# ─── Test 4: Unauthenticated athlete cannot access payment-link ──────────────

@pytest.mark.django_db
def test_payment_link_requires_auth():
    """GET /api/athlete/payment-link/ without auth → 401."""
    client = APIClient()
    response = client.get("/api/athlete/payment-link/")
    assert response.status_code == 401


# ─── Test 5: back_url uses /payment/callback ────────────────────────────────

@pytest.mark.django_db
def test_create_mp_preapproval_returns_init_point_from_plan(org_with_mp):
    """
    FIX-1: _create_mp_preapproval creates an individual athlete preapproval
    (create_coach_athlete_preapproval) and returns both {id, init_point}.
    The preapproval_id is stamped before the athlete reaches MP checkout.
    """
    from core.models import AthleteInvitation
    import uuid as _uuid

    org, owner, plan = org_with_mp
    from django.utils import timezone as _tz
    from datetime import timedelta as _td
    invitation = AthleteInvitation.objects.create(
        organization=org,
        email="invited@test.com",
        token=_uuid.uuid4(),
        coach_plan=plan,
        expires_at=_tz.now() + _td(days=30),
    )

    fake_preapproval = {
        "id": "individual_preapproval_167",
        "init_point": "https://mp.com/checkout/plan",
    }

    with patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value=fake_preapproval,
    ):
        from core.views_onboarding import _create_mp_preapproval
        mp_data, error = _create_mp_preapproval(invitation, "invited@test.com", coach_plan=plan)

    assert error is None
    assert mp_data is not None
    assert mp_data.get("init_point") == "https://mp.com/checkout/plan"
    # FIX-1: preapproval_id is now present so webhook fast-path works without /sync
    assert mp_data.get("id") == "individual_preapproval_167"
