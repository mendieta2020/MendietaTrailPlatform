"""
PR-167f-fix — Sync reconciliation + manual activation

Tests:
1. test_sync_auto_reconciles_1_to_1: 1 sub pending + 1 preapproval → reconciled
2. test_sync_skips_ambiguous: 2 subs + 2 preapprovals same payer → ambiguous, skip
3. test_activate_links_mp_preapproval: activar manualmente busca y asigna preapproval de MP
4. test_activate_without_mp_preapproval: activar sin preapproval → activa sin MP
5. test_webhook_fallback_by_payer_id (unchanged)
6. test_get_mp_user_returns_email (unchanged)
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

SYNC_URL = "/api/billing/athlete-subscriptions/sync/"


# ─── Shared helpers ──────────────────────────────────────────────────────────

def _make_preapproval(id_, payer_id, date_created, status="authorized"):
    return {
        "id": id_,
        "payer_id": payer_id,
        "payer_email": "",        # intentionally empty (production case)
        "status": status,
        "date_created": date_created,
        "preapproval_plan_id": "plan_test_mp",
    }


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def org_with_owner_and_plan():
    """Org, owner, MP credential, one plan."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username="owner_167f", email="owner_167f@test.com", password="pw"
    )
    org = Organization.objects.create(name="Org167f", slug="org-167f")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)
    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan Test", price_ars=5000,
        mp_plan_id="plan_test_mp", is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token="coach_tok",
    )
    return owner, org, plan


@pytest.fixture
def sub_pending(org_with_owner_and_plan):
    """Single pending AthleteSubscription with mp_preapproval_id=None."""
    from core.models import Membership, Athlete, AthleteSubscription

    owner, org, plan = org_with_owner_and_plan
    user = User.objects.create_user(
        username="ath_167f", email="ath@club.com", password="pw"
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    ath = Athlete.objects.create(user=user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=ath, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id=None,
    )
    return owner, org, plan, sub


# ─── Test 1: 1:1 auto-reconcile ──────────────────────────────────────────────

@pytest.mark.django_db
def test_sync_auto_reconciles_1_to_1(sub_pending):
    """
    1 pending sub (no mp_preapproval_id) + 1 authorized unassigned preapproval
    for the same plan → sync auto-links them.
    """
    owner, org, plan, sub = sub_pending
    preapproval = _make_preapproval("preapp_abc", 111222333, "2026-04-16T10:00:00.000-04:00")

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch(
            "integrations.mercadopago.subscriptions.search_preapprovals",
            return_value=[preapproval],
        ),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)  # Pass 1 finds nothing
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert len(data["reconciled"]) == 1
    assert data["reconciled"][0]["sub_id"] == sub.pk
    assert data["reconciled"][0]["reconciled_by"] == "1_to_1"

    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "preapp_abc"
    assert sub.mp_payer_id == "111222333"
    assert sub.status == "active"


# ─── Test 2: ambiguous match — skip ──────────────────────────────────────────

@pytest.mark.django_db
def test_sync_skips_ambiguous(org_with_owner_and_plan):
    """
    2 pending subs + 2 preapprovals with different payer_ids for the same plan
    → ambiguous, neither sub is reconciled.
    """
    from core.models import Membership, Athlete, AthleteSubscription

    owner, org, plan = org_with_owner_and_plan

    for i, email in enumerate(["ath_a@club.com", "ath_b@club.com"]):
        u = User.objects.create_user(username=f"ath_amb_{i}", email=email, password="pw")
        Membership.objects.create(user=u, organization=org, role="athlete", is_active=True)
        a = Athlete.objects.create(user=u, organization=org)
        AthleteSubscription.objects.create(
            athlete=a, organization=org, coach_plan=plan,
            status="pending", mp_preapproval_id=None,
        )

    preapprovals = [
        _make_preapproval("pre_x", 111, "2026-04-16T09:00:00.000-04:00"),
        _make_preapproval("pre_y", 222, "2026-04-16T10:00:00.000-04:00"),
    ]

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch(
            "integrations.mercadopago.subscriptions.search_preapprovals",
            return_value=preapprovals,
        ),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    assert len(res.json()["reconciled"]) == 0

    for sub in AthleteSubscription.objects.filter(organization=org):
        assert sub.mp_preapproval_id is None
        assert sub.status == "pending"


# ─── Test 3: manual activate links MP preapproval ────────────────────────────

@pytest.mark.django_db
def test_activate_links_mp_preapproval(sub_pending):
    """
    Owner clicks 'Activar manualmente'. An authorized preapproval exists for the
    plan in MP → backend links it and returns mp_linked=True.
    """
    owner, org, plan, sub = sub_pending
    preapproval = _make_preapproval("preapp_manual", 555666777, "2026-04-16T10:00:00.000-04:00")

    client = APIClient()
    client.force_authenticate(user=owner)

    with patch(
        "integrations.mercadopago.subscriptions.search_preapprovals",
        return_value=[preapproval],
    ):
        res = client.post(f"/api/billing/athlete-subscriptions/{sub.pk}/activate/")

    assert res.status_code == 200
    data = res.json()
    assert data["mp_linked"] is True
    assert data["status"] == "active"

    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "preapp_manual"
    assert sub.mp_payer_id == "555666777"
    assert sub.status == "active"
    assert sub.last_payment_at is not None
    assert sub.next_payment_at is not None


# ─── Test 4: manual activate without MP preapproval ──────────────────────────

@pytest.mark.django_db
def test_activate_without_mp_preapproval(sub_pending):
    """
    Owner clicks 'Activar manualmente'. No authorized preapproval available in MP
    (cash/transfer payment) → backend activates without MP, mp_linked=False.
    """
    owner, org, plan, sub = sub_pending

    client = APIClient()
    client.force_authenticate(user=owner)

    with patch(
        "integrations.mercadopago.subscriptions.search_preapprovals",
        return_value=[],  # no preapprovals available
    ):
        res = client.post(f"/api/billing/athlete-subscriptions/{sub.pk}/activate/")

    assert res.status_code == 200
    data = res.json()
    assert data["mp_linked"] is False
    assert data["status"] == "active"

    sub.refresh_from_db()
    assert sub.mp_preapproval_id is None
    assert sub.status == "active"
    assert sub.last_payment_at is not None
    assert sub.next_payment_at is not None


# ─── Test 5: webhook fallback by mp_payer_id ─────────────────────────────────

@pytest.mark.django_db
def test_webhook_fallback_by_payer_id(sub_pending):
    """
    Webhook arrives for unknown preapproval_id. Sub has mp_payer_id already set
    from a prior sync → fallback matches by mp_payer_id (no extra API call).
    """
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    owner, org, plan, sub = sub_pending

    sub.mp_payer_id = "236253210"
    sub.save(update_fields=["mp_payer_id"])

    mp_preapproval_data = {
        "id": "brand_new_preapproval",
        "payer_id": 236253210,
        "payer_email": "",
        "status": "authorized",
        "preapproval_plan_id": plan.mp_plan_id,
        "date_created": "2026-04-16T12:00:00.000-04:00",
    }

    class _FakeCred:
        def __init__(self, _org):
            self.organization = _org
            self.organization_id = _org.pk
            self.access_token = "coach_tok"

    def fake_fetch(preapproval_id):
        return mp_preapproval_data, _FakeCred(org)

    with patch(
        "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
        side_effect=fake_fetch,
    ):
        result = process_athlete_subscription_webhook({"id": "brand_new_preapproval"})

    assert result["outcome"] in ("updated", "reconciled")
    sub.refresh_from_db()
    assert sub.status == "active"
    assert sub.mp_preapproval_id == "brand_new_preapproval"


# ─── Test 6: get_mp_user returns email ───────────────────────────────────────

@pytest.mark.django_db
def test_get_mp_user_returns_email():
    """get_mp_user parses the MP /users/{id} response correctly."""
    from integrations.mercadopago.subscriptions import get_mp_user

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "id": 236253210,
        "email": "natalia@club.com",
        "first_name": "Natalia",
        "last_name": "Test",
    }
    fake_response.raise_for_status = lambda: None

    with patch(
        "integrations.mercadopago.subscriptions._requests.get",
        return_value=fake_response,
    ) as mock_get:
        result = get_mp_user("fake_token", "236253210")

    assert result["email"] == "natalia@club.com"
    call_args = mock_get.call_args
    assert "/users/236253210" in call_args[0][0]
    # Law 6: access_token must NOT appear in positional args (only in headers)
    assert "fake_token" not in str(call_args[0])
