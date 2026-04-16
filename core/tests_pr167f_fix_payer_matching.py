"""
PR-167f-fix — Reconciliación por payer_id (lookup email via MP /users/{id})

Tests:
1. Sync matches sub by payer_id → email lookup (MP search returns no payer_email)
2. Sync skips preapproval already assigned in DB
3. Sync picks newest preapproval when athlete has duplicates (paid twice)
4. Sync does not match wrong athlete (payer resolves to unknown email)
5. Sync stores mp_payer_id on matched sub
6. Webhook fallback matches by mp_payer_id (no extra API call)
7. get_mp_user returns email from MP /users/{id}
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

SYNC_URL = "/api/billing/athlete-subscriptions/sync/"


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def payer_setup():
    """
    Org with owner, MP credential, one plan, and two athlete subs
    (Natalia + Tomas), both pending with mp_preapproval_id=None.
    """
    from core.models import (
        Organization, Membership, CoachPricingPlan,
        OrgOAuthCredential, Athlete, AthleteSubscription,
    )

    owner = User.objects.create_user(
        username="owner_payer", email="owner_payer@test.com", password="pw"
    )
    org = Organization.objects.create(name="OrgPayer", slug="org-payer")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan Regalo", price_ars=5000,
        mp_plan_id="plan_regalo_mp", is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token="coach_token_x",
    )

    # Natalia (payer_id=236253210) — will have authorized preapproval
    natalia_user = User.objects.create_user(
        username="natalia_p", email="natalia@club.com", password="pw"
    )
    Membership.objects.create(user=natalia_user, organization=org, role="athlete", is_active=True)
    natalia_ath = Athlete.objects.create(user=natalia_user, organization=org)
    sub_natalia = AthleteSubscription.objects.create(
        athlete=natalia_ath, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id=None,
    )

    # Tomas — never paid
    tomas_user = User.objects.create_user(
        username="tomas_p", email="tomas@club.com", password="pw"
    )
    Membership.objects.create(user=tomas_user, organization=org, role="athlete", is_active=True)
    tomas_ath = Athlete.objects.create(user=tomas_user, organization=org)
    sub_tomas = AthleteSubscription.objects.create(
        athlete=tomas_ath, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id=None,
    )

    return owner, org, plan, sub_natalia, sub_tomas


def _make_preapproval(id_, payer_id, date_created, status="authorized"):
    return {
        "id": id_,
        "payer_id": payer_id,
        "payer_email": "",        # intentionally empty (production case)
        "status": status,
        "date_created": date_created,
        "preapproval_plan_id": "plan_regalo_mp",
    }


# ─── Test 1: match by payer_id → email lookup ────────────────────────────────

@pytest.mark.django_db
def test_sync_matches_by_payer_id_email_lookup(payer_setup):
    """
    MP search returns payer_email=''. Sync resolves email via GET /users/{payer_id}
    and stamps mp_preapproval_id + mp_payer_id on Natalia's sub.
    Tomas's sub stays pending (his payer_id doesn't resolve to any sub email).
    """
    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    preapproval = _make_preapproval("857beb0abc", 236253210, "2026-04-16T10:00:00.000-04:00")

    def fake_search(access_token, plan_id, status=None):
        return [preapproval]

    def fake_get_mp_user(access_token, user_id):
        if str(user_id) == "236253210":
            return {"email": "natalia@club.com", "first_name": "Natalia"}
        return {"email": ""}

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch("integrations.mercadopago.subscriptions.search_preapprovals", side_effect=fake_search),
        patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        # Pass 1 finds no subs with mp_preapproval_id → returns empty
        mock_http.return_value = MagicMock(status_code=404)
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    data = res.json()
    assert len(data["reconciled"]) == 1
    assert data["reconciled"][0]["sub_id"] == sub_natalia.pk
    assert data["reconciled"][0]["reconciled_by"] == "payer_id_lookup"

    sub_natalia.refresh_from_db()
    assert sub_natalia.mp_preapproval_id == "857beb0abc"
    assert sub_natalia.mp_payer_id == "236253210"
    assert sub_natalia.status == "active"

    sub_tomas.refresh_from_db()
    assert sub_tomas.status == "pending"
    assert sub_tomas.mp_preapproval_id is None


# ─── Test 2: skips already-assigned preapproval ───────────────────────────────

@pytest.mark.django_db
def test_sync_skips_already_assigned_preapprovals(payer_setup):
    """
    If preapproval is already linked to another sub, it must not be re-assigned.
    """
    from core.models import AthleteSubscription
    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    # Pre-assign the preapproval to Natalia's sub (simulates prior sync)
    sub_natalia.mp_preapproval_id = "857beb0abc"
    sub_natalia.save(update_fields=["mp_preapproval_id"])

    # Create a third athlete
    third_user = User.objects.create_user(
        username="third_p", email="third@club.com", password="pw"
    )
    from core.models import Membership, Athlete
    Membership.objects.create(user=third_user, organization=org, role="athlete", is_active=True)
    third_ath = Athlete.objects.create(user=third_user, organization=org)
    sub_third = AthleteSubscription.objects.create(
        athlete=third_ath, organization=org, coach_plan=plan,
        status="pending", mp_preapproval_id=None,
    )

    preapproval = _make_preapproval("857beb0abc", 236253210, "2026-04-16T10:00:00.000-04:00")

    def fake_get_mp_user(access_token, user_id):
        return {"email": "third@club.com"}  # resolves to third athlete

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[preapproval]),
        patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    # preapproval 857beb0abc is already assigned → third sub must NOT get it
    sub_third.refresh_from_db()
    assert sub_third.mp_preapproval_id is None
    assert sub_third.status == "pending"


# ─── Test 3: picks newest when duplicate preapprovals ────────────────────────

@pytest.mark.django_db
def test_sync_picks_newest_when_duplicate_preapprovals(payer_setup):
    """
    Natalia paid twice → two authorized preapprovals. Only the newest is assigned.
    """
    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    older = _make_preapproval("414ae89aaa", 236253210, "2026-04-15T09:00:00.000-04:00")
    newer = _make_preapproval("857beb0abc", 236253210, "2026-04-16T10:00:00.000-04:00")

    def fake_get_mp_user(access_token, user_id):
        return {"email": "natalia@club.com"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[older, newer]),
        patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    sub_natalia.refresh_from_db()
    # Only the newest preapproval is assigned
    assert sub_natalia.mp_preapproval_id == "857beb0abc"
    assert sub_natalia.status == "active"


# ─── Test 4: does not match wrong athlete ────────────────────────────────────

@pytest.mark.django_db
def test_sync_does_not_match_wrong_athlete(payer_setup):
    """
    payer resolves to an email not in our DB → no sub is matched.
    """
    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    preapproval = _make_preapproval("999xyz", 999999, "2026-04-16T10:00:00.000-04:00")

    def fake_get_mp_user(access_token, user_id):
        return {"email": "unknown@nowhere.com"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[preapproval]),
        patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)
        res = client.post(SYNC_URL)

    assert res.status_code == 200
    assert len(res.json()["reconciled"]) == 0
    sub_natalia.refresh_from_db()
    assert sub_natalia.mp_preapproval_id is None


# ─── Test 5: stores mp_payer_id ──────────────────────────────────────────────

@pytest.mark.django_db
def test_sync_stores_mp_payer_id(payer_setup):
    """mp_payer_id field is persisted on successful match."""
    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    preapproval = _make_preapproval("857beb0abc", 236253210, "2026-04-16T10:00:00.000-04:00")

    def fake_get_mp_user(access_token, user_id):
        return {"email": "natalia@club.com"}

    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[preapproval]),
        patch("integrations.mercadopago.subscriptions.get_mp_user", side_effect=fake_get_mp_user),
        patch("core.views_billing.http_requests.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=404)
        client.post(SYNC_URL)

    sub_natalia.refresh_from_db()
    assert sub_natalia.mp_payer_id == "236253210"


# ─── Test 6: webhook fallback by mp_payer_id ─────────────────────────────────

@pytest.mark.django_db
def test_webhook_fallback_by_payer_id(payer_setup):
    """
    Webhook arrives for unknown preapproval_id. Sub has mp_payer_id already set
    from a prior sync → fallback matches by mp_payer_id (no extra API call).
    """
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    owner, org, plan, sub_natalia, sub_tomas = payer_setup

    # Simulate prior sync: Natalia's sub has payer_id stamped but preapproval unknown
    sub_natalia.mp_payer_id = "236253210"
    sub_natalia.save(update_fields=["mp_payer_id"])

    mp_preapproval_data = {
        "id": "brand_new_preapproval",
        "payer_id": 236253210,
        "payer_email": "",
        "status": "authorized",
        "preapproval_plan_id": "plan_regalo_mp",
        "date_created": "2026-04-16T12:00:00.000-04:00",
    }

    def fake_fetch(preapproval_id):
        return mp_preapproval_data, _make_cred(org)

    class _make_cred:
        def __init__(self, org):
            self.organization = org
            self.organization_id = org.pk
            self.access_token = "coach_token_x"

    with patch(
        "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
        side_effect=fake_fetch,
    ):
        result = process_athlete_subscription_webhook({"id": "brand_new_preapproval"})

    assert result["outcome"] in ("updated", "reconciled")
    sub_natalia.refresh_from_db()
    assert sub_natalia.status == "active"
    assert sub_natalia.mp_preapproval_id == "brand_new_preapproval"


# ─── Test 7: get_mp_user returns email ───────────────────────────────────────

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
    # Verify endpoint path
    assert "/users/236253210" in call_args[0][0]
    # Law 6: access_token must NOT appear in positional args (only in headers)
    assert "fake_token" not in str(call_args[0])
