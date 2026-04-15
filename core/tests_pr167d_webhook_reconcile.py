"""
PR-167d — Webhook fallback reconciliation tests.

Tests:
1. Webhook reconciles by payer_email when preapproval_id is unknown
2. Webhook is idempotent on second authorized event
3. Webhook logs not_found when no match found
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model

User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def org_with_mp_167d():
    """Org with MP credential + CoachPricingPlan + owner."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username="owner167d", email="owner167d@test.com", password="pw"
    )
    org = Organization.objects.create(name="Org167d", slug="org-167d")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Plan Regalo",
        price_ars=100,
        mp_plan_id="mp_plan_regalo",
        is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="fake_coach_token",
    )
    return org, owner, plan


@pytest.fixture
def athlete_sub_no_preapproval(org_with_mp_167d):
    """Athlete with AthleteSubscription pending but NO mp_preapproval_id (the broken case)."""
    from core.models import Membership, Athlete, AthleteSubscription

    org, owner, plan = org_with_mp_167d
    athlete_user = User.objects.create_user(
        username="natalia167d", email="natalia@example.com", password="pw"
    )
    Membership.objects.create(
        user=athlete_user, organization=org, role="athlete", is_active=True
    )
    athlete = Athlete.objects.create(user=athlete_user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status="pending",
        mp_preapproval_id=None,  # Not yet set — simulates broken create flow
    )
    return athlete_user, sub, org, plan


# ─── Test 1: reconcile by payer_email ────────────────────────────────────────

@pytest.mark.django_db
def test_webhook_reconciles_by_payer_email_when_preapproval_id_unknown(
    athlete_sub_no_preapproval,
):
    """
    When mp_preapproval_id is not set, the fallback fetches the preapproval
    from MP, matches by payer_email + plan_id, sets the id, and marks active.
    """
    athlete_user, sub, org, plan = athlete_sub_no_preapproval
    real_preapproval_id = "mp_real_preapproval_999"

    fake_mp_response = {
        "id": real_preapproval_id,
        "status": "authorized",
        "payer_email": "natalia@example.com",
        "preapproval_plan_id": "mp_plan_regalo",
    }

    fake_http_response = MagicMock()
    fake_http_response.status_code = 200
    fake_http_response.json.return_value = fake_mp_response

    webhook_payload = {
        "id": real_preapproval_id,
        "status": "authorized",
    }

    with patch("integrations.mercadopago.athlete_webhook.requests.get", return_value=fake_http_response):
        from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
        result = process_athlete_subscription_webhook(webhook_payload)

    assert result["outcome"] == "reconciled"
    assert result["preapproval_id"] == real_preapproval_id

    sub.refresh_from_db()
    assert sub.status == "active"
    assert sub.mp_preapproval_id == real_preapproval_id
    assert sub.last_payment_at is not None
    assert sub.next_payment_at is not None


# ─── Test 2: idempotent on second authorized event ───────────────────────────

@pytest.mark.django_db
def test_webhook_idempotent_on_second_authorized_event(org_with_mp_167d):
    """
    A second 'authorized' webhook for the same preapproval_id that is already
    active returns 'noop' without changing data.
    """
    from core.models import Membership, Athlete, AthleteSubscription
    from django.utils import timezone

    org, owner, plan = org_with_mp_167d
    athlete_user = User.objects.create_user(
        username="atleta_idem", email="idem@example.com", password="pw"
    )
    Membership.objects.create(
        user=athlete_user, organization=org, role="athlete", is_active=True
    )
    athlete = Athlete.objects.create(user=athlete_user, organization=org)
    now = timezone.now()
    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status="active",
        mp_preapproval_id="mp_already_active",
        last_payment_at=now,
        next_payment_at=now,
    )

    webhook_payload = {"id": "mp_already_active", "status": "authorized"}

    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
    result = process_athlete_subscription_webhook(webhook_payload)

    assert result["outcome"] == "noop"
    sub.refresh_from_db()
    assert sub.status == "active"
    # Payment dates should not have changed
    assert sub.last_payment_at == now


# ─── Test 3: not_found when no match ─────────────────────────────────────────

@pytest.mark.django_db
def test_webhook_logs_not_found_when_no_match(org_with_mp_167d):
    """
    When neither fast-path nor fallback finds a match, outcome is 'not_found'.
    """
    unknown_payload = {"id": "mp_completely_unknown_999", "status": "authorized"}

    # MP returns 404 for unknown preapproval
    fake_http_response = MagicMock()
    fake_http_response.status_code = 404

    with patch("integrations.mercadopago.athlete_webhook.requests.get", return_value=fake_http_response):
        from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
        result = process_athlete_subscription_webhook(unknown_payload)

    assert result["outcome"] == "not_found"
    assert result["preapproval_id"] == "mp_completely_unknown_999"
