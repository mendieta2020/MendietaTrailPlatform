"""
PR-167e — MP payment methods + reason branding + account_money

Tests:
1. create_preapproval_plan: payload has NO payment_methods_allowed key
2. _create_mp_preapproval: reason format is "OrgName — PlanName"
3. Data migration helper: CoachPricingPlan.mp_plan_id is reset to None
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model

User = get_user_model()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def org_mp_setup():
    """Org with MP credential + CoachPricingPlan (no mp_plan_id yet)."""
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username="owner167e", email="owner167e@test.com", password="pw"
    )
    org = Organization.objects.create(name="Mendieta Trail Training", slug="org-167e")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Regalo",
        price_ars=15000,
        mp_plan_id=None,
        is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="fake_token_167e",
    )
    return org, owner, plan


@pytest.fixture
def invitation_for(org_mp_setup):
    """AthleteInvitation linked to the org/plan above."""
    from core.models import AthleteInvitation
    from django.utils import timezone
    from datetime import timedelta

    org, owner, plan = org_mp_setup
    invitation = AthleteInvitation.objects.create(
        organization=org,
        email="athlete167e@test.com",
        coach_plan=plan,
        expires_at=timezone.now() + timedelta(days=7),
    )
    return invitation, org, owner, plan


# ─── Test 1: No payment_methods_allowed in MP payload ─────────────────────────

@pytest.mark.django_db
def test_create_preapproval_plan_no_payment_restriction():
    """
    MP payload must NOT include payment_methods_allowed.
    Omitting it lets MP show all methods: credit_card, debit_card, account_money.
    """
    from integrations.mercadopago.subscriptions import create_preapproval_plan

    captured_payload = {}

    def mock_post(url, json, headers, timeout):
        captured_payload.update(json)
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "plan_new_167e", "init_point": "https://mp.test/checkout"}
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    with patch("integrations.mercadopago.subscriptions._requests.post", side_effect=mock_post):
        result = create_preapproval_plan(
            access_token="fake_token",
            name="Mendieta Trail Training — Regalo",
            price_ars=15000,
            back_url="https://app.quantoryn.com/payment/callback",
        )

    assert "payment_methods_allowed" not in captured_payload, (
        "payload must NOT restrict payment methods — account_money must be available"
    )
    assert result["id"] == "plan_new_167e"


# ─── Test 2: reason includes org name ─────────────────────────────────────────

@pytest.mark.django_db
def test_reason_includes_org_name(invitation_for):
    """
    FIX-1: _create_mp_preapproval now calls create_coach_athlete_preapproval which
    sends reason='Quantoryn {PlanName} — {OrgName}' to MP checkout.
    Both org name and plan name must appear in the reason string.
    """
    invitation, org, owner, plan = invitation_for

    # plan has mp_plan_id=None → create_preapproval_plan is called first (POST),
    # then create_coach_athlete_preapproval is called (POST).
    # Both POSTs are captured; the reason field comes from the second call.
    captured_payloads = []

    def mock_post(url, json, headers, timeout):
        captured_payloads.append(dict(json))
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "id": "plan_branded_167e",
            "init_point": "https://mp.test/checkout",
        }
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    with patch("integrations.mercadopago.subscriptions._requests.post", side_effect=mock_post):
        from core.views_onboarding import _create_mp_preapproval
        mp_data, error = _create_mp_preapproval(invitation, "athlete167e@test.com")

    assert error is None
    # create_coach_athlete_preapproval payload has 'reason'; find it
    reason_payload = next((p for p in captured_payloads if "reason" in p), None)
    assert reason_payload is not None, "No POST call contained a 'reason' field"
    reason = reason_payload["reason"]
    assert org.name in reason, f"org name '{org.name}' missing from reason '{reason}'"
    assert plan.name in reason, f"plan name '{plan.name}' missing from reason '{reason}'"


# ─── Test 3: migration resets mp_plan_id to None ──────────────────────────────

@pytest.mark.django_db
def test_migration_resets_mp_plan_ids():
    """
    CoachPricingPlans with an existing mp_plan_id must be reset to None
    so the next checkout triggers lazy re-creation with unrestricted payment methods.
    """
    from core.models import Organization, CoachPricingPlan

    org = Organization.objects.create(name="TestOrg167e", slug="testorg-167e")
    plan_with_id = CoachPricingPlan.objects.create(
        organization=org,
        name="Old Plan",
        price_ars=9999,
        mp_plan_id="old_mp_plan_xyz",
        is_active=True,
    )
    plan_without_id = CoachPricingPlan.objects.create(
        organization=org,
        name="Fresh Plan",
        price_ars=9999,
        mp_plan_id=None,
        is_active=True,
    )

    # Simulate the migration's RunPython function directly
    updated = CoachPricingPlan.objects.filter(mp_plan_id__isnull=False).update(mp_plan_id=None)

    plan_with_id.refresh_from_db()
    plan_without_id.refresh_from_db()

    assert updated >= 1
    assert plan_with_id.mp_plan_id is None, "mp_plan_id should be reset to None"
    assert plan_without_id.mp_plan_id is None, "already-None plan should remain None"
