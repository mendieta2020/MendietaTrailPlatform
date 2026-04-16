"""
PR-167d — AthleteSubscriptionSyncView tests.

Tests:
1. Sync endpoint reconciles pending → active for subs with mp_preapproval_id
2. Sync endpoint is owner-only (athlete gets 403)
3. Sync endpoint skips subs without mp_preapproval_id
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

SYNC_URL = "/api/billing/athlete-subscriptions/sync/"


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sync_setup():
    """Owner org with MP credential and two athlete subs."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential, Athlete, AthleteSubscription

    owner = User.objects.create_user(
        username="owner_sync", email="owner_sync@test.com", password="pw"
    )
    org = Organization.objects.create(name="OrgSync", slug="org-sync")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org, name="Sync Plan", price_ars=500,
        mp_plan_id="mp_sync_plan", is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token="sync_token",
    )

    # Sub with preapproval_id (should be synced)
    athlete_a = User.objects.create_user(username="sync_a", email="sync_a@test.com", password="pw")
    Membership.objects.create(user=athlete_a, organization=org, role="athlete", is_active=True)
    ath_a = Athlete.objects.create(user=athlete_a, organization=org)
    sub_a = AthleteSubscription.objects.create(
        athlete=ath_a, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id="preaprob_sync_a",
    )

    # Sub WITHOUT preapproval_id (should be skipped)
    athlete_b = User.objects.create_user(username="sync_b", email="sync_b@test.com", password="pw")
    Membership.objects.create(user=athlete_b, organization=org, role="athlete", is_active=True)
    ath_b = Athlete.objects.create(user=athlete_b, organization=org)
    sub_b = AthleteSubscription.objects.create(
        athlete=ath_b, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id=None,
    )

    return owner, org, sub_a, sub_b


# ─── Test 1: reconciles pending → active ─────────────────────────────────────

@pytest.mark.django_db
def test_sync_endpoint_reconciles_pending_to_active(sync_setup):
    """POST /sync/ fetches MP status, transitions pending sub to active."""
    owner, org, sub_a, sub_b = sync_setup

    fake_mp_response = MagicMock()
    fake_mp_response.status_code = 200
    fake_mp_response.json.return_value = {"status": "authorized"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with patch("core.views_billing.http_requests.get", return_value=fake_mp_response):
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert len(data["reconciled"]) == 1
    assert data["reconciled"][0]["sub_id"] == sub_a.pk
    assert data["reconciled"][0]["old_status"] == "pending"
    assert data["reconciled"][0]["new_status"] == "active"
    assert data["errors"] == []

    sub_a.refresh_from_db()
    assert sub_a.status == "active"


# ─── Test 2: owner-only ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sync_endpoint_owner_only(sync_setup):
    """Athlete user cannot access the sync endpoint (gets 403)."""
    owner, org, sub_a, sub_b = sync_setup
    from core.models import AthleteSubscription
    # Use athlete_a user (created in fixture)
    athlete_user = sub_a.athlete.user

    client = APIClient()
    client.force_authenticate(user=athlete_user)
    res = client.post(SYNC_URL)

    # Athletes don't have owner/admin membership → BillingOrgMixin returns None → 403
    assert res.status_code == 403


# ─── Test 3: Pass 2 searches MP by plan_id for subs without mp_preapproval_id ─

@pytest.mark.django_db
def test_sync_endpoint_searches_by_plan_for_subs_without_preapproval_id(sync_setup):
    """
    PR-167f: subs without mp_preapproval_id trigger a Pass-2 search by plan_id.
    When MP returns no matching authorized preapproval, the sub stays pending.
    """
    owner, org, sub_a, sub_b = sync_setup

    # Make sub_a already active so Pass 1 has nothing to process
    sub_a.status = "active"
    sub_a.save(update_fields=["status"])

    client = APIClient()
    client.force_authenticate(user=owner)

    # Pass 2 will call search_preapprovals — return empty list (no match)
    with patch(
        "integrations.mercadopago.subscriptions.search_preapprovals",
        return_value=[],
    ) as mock_search:
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert data["reconciled"] == []
    # search_preapprovals must be called for sub_b's plan
    mock_search.assert_called_once()

    sub_b.refresh_from_db()
    assert sub_b.status == "pending"  # unchanged — no match found
