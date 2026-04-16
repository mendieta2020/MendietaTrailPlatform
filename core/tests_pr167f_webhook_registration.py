"""
PR-167f — MP webhook registration + smart sync + payment notifications.

Tests:
1. create_preapproval_plan payload includes notification_url
2. search_preapprovals calls MP API with correct params
3. Sync reconciles sub with mp_preapproval_id=None by searching MP by plan_id
4. Sync sends owner notification when reconciled sub becomes active
5. Webhook handler sends owner notification when sub transitions to active
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

SYNC_URL = "/api/billing/athlete-subscriptions/sync/"


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def base_org():
    """Org with owner, MP credential, and a plan that has mp_plan_id."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username="owner_167f", email="owner_167f@test.com", password="pw"
    )
    org = Organization.objects.create(name="Org167f", slug="org-167f")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Plan Alpha",
        price_ars=1000,
        mp_plan_id="mp_plan_alpha",
        is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token="test_coach_token"
    )
    return owner, org, plan


@pytest.fixture
def sub_without_preapproval(base_org):
    """Athlete sub with mp_preapproval_id=None (the common case after preapproval_plan flow)."""
    from core.models import Athlete, AthleteSubscription, Membership

    owner, org, plan = base_org
    athlete_user = User.objects.create_user(
        username="ath_167f", email="ath_167f@test.com", password="pw",
        first_name="Ana", last_name="Lopez",
    )
    Membership.objects.create(user=athlete_user, organization=org, role="athlete", is_active=True)
    ath = Athlete.objects.create(user=athlete_user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=ath,
        organization=org,
        coach_plan=plan,
        status="pending",
        mp_preapproval_id=None,
    )
    return owner, org, plan, ath, sub, athlete_user


# ─── Test 1: notification_url in create_preapproval_plan ─────────────────────

@pytest.mark.django_db
def test_create_preapproval_plan_includes_notification_url():
    """Payload sent to MP must contain notification_url pointing to our athlete webhook."""
    from integrations.mercadopago.subscriptions import create_preapproval_plan

    captured_payloads = []

    def fake_post(url, json=None, headers=None, timeout=None):
        captured_payloads.append(json)
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "plan_abc123"}
        return mock_resp

    with patch("integrations.mercadopago.subscriptions._requests.post", side_effect=fake_post):
        result = create_preapproval_plan(
            access_token="fake_token",
            name="Test Plan",
            price_ars=500,
        )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert "notification_url" in payload
    assert "/api/webhooks/mercadopago/athlete/" in payload["notification_url"]
    assert result["id"] == "plan_abc123"


# ─── Test 2: search_preapprovals calls MP API with correct params ─────────────

@pytest.mark.django_db
def test_search_preapprovals_calls_mp_api():
    """search_preapprovals must call /preapproval/search with preapproval_plan_id and status."""
    from integrations.mercadopago.subscriptions import search_preapprovals

    fake_results = [{"id": "preapp_1", "payer_email": "a@b.com", "status": "authorized"}]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": fake_results}

    with patch("integrations.mercadopago.subscriptions._requests.get", return_value=mock_resp) as mock_get:
        results = search_preapprovals("token_xyz", "plan_123", status="authorized")

    assert results == fake_results
    call_kwargs = mock_get.call_args
    assert "preapproval/search" in call_kwargs[0][0]
    params = call_kwargs[1]["params"]
    assert params["preapproval_plan_id"] == "plan_123"
    assert params["status"] == "authorized"
    # Law 6: access_token must NOT appear in the logged call params
    assert "token_xyz" not in str(params)


# ─── Test 3: sync reconciles sub with mp_preapproval_id=None by plan search ──

@pytest.mark.django_db
def test_sync_reconciles_by_plan_search(sub_without_preapproval):
    """
    POST /sync/ must find authorized preapprovals for subs without mp_preapproval_id
    by searching MP by plan_id and matching payer_email.
    """
    owner, org, plan, ath, sub, athlete_user = sub_without_preapproval

    # payer_email is empty (production case) — payer_id is used to resolve email
    fake_search_results = [
        {
            "id": "discovered_preapproval_id",
            "payer_id": 111222333,
            "payer_email": "",
            "status": "authorized",
            "date_created": "2026-04-16T10:00:00.000-04:00",
        }
    ]

    def fake_get_mp_user(access_token, user_id):
        return {"email": "ath_167f@test.com"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with patch(
        "integrations.mercadopago.subscriptions.search_preapprovals",
        return_value=fake_search_results,
    ):
        with patch(
            "integrations.mercadopago.subscriptions.get_mp_user",
            side_effect=fake_get_mp_user,
        ):
            with patch(
                "integrations.mercadopago.athlete_webhook._notify_owner_payment_received"
            ):
                res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert len(data["reconciled"]) == 1
    reconciled_entry = data["reconciled"][0]
    assert reconciled_entry["sub_id"] == sub.pk
    assert reconciled_entry["old_status"] == "pending"
    assert reconciled_entry["new_status"] == "active"
    assert reconciled_entry.get("reconciled_by") == "payer_id_lookup"

    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "discovered_preapproval_id"
    assert sub.status == "active"


# ─── Test 4: sync sends owner notification on reconciliation ─────────────────

@pytest.mark.django_db
def test_sync_sends_owner_notification(sub_without_preapproval):
    """
    When sync reconciles a sub to active via plan search, it must create
    an InternalMessage to the org owner.
    """
    from core.models import InternalMessage

    owner, org, plan, ath, sub, athlete_user = sub_without_preapproval

    fake_search_results = [
        {
            "id": "notif_preapproval_id",
            "payer_id": 444555666,
            "payer_email": "",
            "status": "authorized",
            "date_created": "2026-04-16T10:00:00.000-04:00",
        }
    ]

    def fake_get_mp_user(access_token, user_id):
        return {"email": "ath_167f@test.com"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=fake_search_results):
        with patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user):
            res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert data["notifications_sent"] >= 1

    msg = InternalMessage.objects.filter(
        organization=org,
        recipient=owner,
        alert_type="payment_received",
    ).first()
    assert msg is not None
    assert "Plan Alpha" in msg.content


# ─── Test 5: webhook sends owner notification on status → active ──────────────

@pytest.mark.django_db
def test_webhook_sends_owner_notification(sub_without_preapproval):
    """
    process_athlete_subscription_webhook must create an InternalMessage to the
    org owner when a subscription transitions to active via the fast path.
    """
    from core.models import AthleteSubscription, InternalMessage
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    owner, org, plan, ath, sub, athlete_user = sub_without_preapproval

    # Give the sub a preapproval_id so it hits the fast path
    sub.mp_preapproval_id = "webhook_preapproval_id"
    sub.save(update_fields=["mp_preapproval_id"])

    payload = {"id": "webhook_preapproval_id", "status": "authorized"}
    result = process_athlete_subscription_webhook(payload)

    assert result["outcome"] == "updated"

    sub.refresh_from_db()
    assert sub.status == "active"

    msg = InternalMessage.objects.filter(
        organization=org,
        recipient=owner,
        alert_type="payment_received",
    ).first()
    assert msg is not None
    assert "Plan Alpha" in msg.content
