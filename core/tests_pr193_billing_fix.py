"""
PR-193 — Billing fixes tests.

T1: Webhook with mismatched email + matching plan_id → sub stamped.
T2: 2 subs matching same plan_id → ambiguous, NOT stamped, logs warning.
T3: 0 subs matching plan_id → not_found, no crash.
T4: After T1 stamp, second webhook → fast path works.
T5: AthleteSubscription visible in Django Admin → 200 OK.
"""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings

User = get_user_model()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_org_plan_cred(suffix="193"):
    from core.models import Organization, Membership, CoachPricingPlan, OrgOAuthCredential

    owner = User.objects.create_user(
        username=f"owner_{suffix}", email=f"owner_{suffix}@test.com", password="pw"
    )
    org = Organization.objects.create(name=f"Org{suffix}", slug=f"org-{suffix}")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)
    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan 193", price_ars=9000,
        mp_plan_id="mp_plan_193", is_active=True,
    )
    OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token="tok_193",
    )
    return owner, org, plan


def _make_athlete_sub(org, plan, email, status="pending", mp_preapproval_id=None):
    from core.models import Membership, Athlete, AthleteSubscription

    user = User.objects.create_user(
        username=email.replace("@", "_at_"), email=email, password="pw"
    )
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    ath = Athlete.objects.create(user=user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=ath, organization=org, coach_plan=plan,
        status=status, mp_preapproval_id=mp_preapproval_id,
    )
    return sub


class _FakeCred:
    def __init__(self, org):
        self.organization = org
        self.organization_id = org.pk
        self.access_token = "tok_193"


# ── T1: email mismatch + plan_id match → sub stamped ─────────────────────────

@pytest.mark.django_db
def test_reconcile_by_plan_id_stamps_single_match():
    """
    Athlete used a different MP email. Strategies 1-3 all miss.
    Strategy 4 finds exactly 1 pending sub for the plan → stamps mp_preapproval_id.
    """
    from integrations.mercadopago.athlete_webhook import _reconcile_by_payer

    _, org, plan = _make_org_plan_cred("193a")
    sub = _make_athlete_sub(org, plan, email="natalia@quantoryn.com")

    mp_data = {
        "id": "131210349711",
        "payer_id": "",           # empty → strategy 1 and 3 skip
        "payer_email": "",        # empty → strategy 2 skips
        "preapproval_plan_id": "mp_plan_193",
        "status": "authorized",
    }

    result = _reconcile_by_payer(mp_data, _FakeCred(org))

    assert result is not None
    assert result.pk == sub.pk

    sub.refresh_from_db()
    assert sub.mp_preapproval_id == "131210349711"


# ── T2: 2 matching subs → ambiguous, not stamped ─────────────────────────────

@pytest.mark.django_db
def test_reconcile_by_plan_id_ambiguous_not_stamped():
    """
    2 pending subs for the same plan → strategy 4 returns None, neither is stamped.
    """
    from integrations.mercadopago.athlete_webhook import _reconcile_by_payer

    _, org, plan = _make_org_plan_cred("193b")
    _make_athlete_sub(org, plan, email="ath1_193b@test.com")
    _make_athlete_sub(org, plan, email="ath2_193b@test.com")

    mp_data = {
        "id": "preapp_ambiguous",
        "payer_id": "",
        "payer_email": "",
        "preapproval_plan_id": "mp_plan_193",
        "status": "authorized",
    }

    with patch("integrations.mercadopago.athlete_webhook.logger") as mock_log:
        result = _reconcile_by_payer(mp_data, _FakeCred(org))

    assert result is None
    # Warning logged for ambiguous
    warning_calls = [
        c for c in mock_log.warning.call_args_list
        if "reconcile_ambiguous" in str(c)
    ]
    assert len(warning_calls) == 1

    from core.models import AthleteSubscription
    for s in AthleteSubscription.objects.filter(organization=org):
        assert s.mp_preapproval_id is None


# ── T3: 0 matching subs → not_found, no crash ────────────────────────────────

@pytest.mark.django_db
def test_reconcile_by_plan_id_zero_match_no_crash():
    """
    No pending subs for the plan → strategy 4 count == 0, falls through, returns None.
    """
    from integrations.mercadopago.athlete_webhook import _reconcile_by_payer

    _, org, plan = _make_org_plan_cred("193c")
    # No subs created for this org/plan

    mp_data = {
        "id": "preapp_ghost",
        "payer_id": "",
        "payer_email": "",
        "preapproval_plan_id": "mp_plan_193",
        "status": "authorized",
    }

    result = _reconcile_by_payer(mp_data, _FakeCred(org))
    assert result is None


# ── T4: after stamp, second webhook hits fast path ────────────────────────────

@pytest.mark.django_db
def test_fast_path_after_strategy4_stamp():
    """
    Second webhook for the same preapproval_id (now stamped) → fast path resolves it.
    """
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    _, org, plan = _make_org_plan_cred("193d")
    sub = _make_athlete_sub(
        org, plan, email="ath_193d@test.com",
        status="pending", mp_preapproval_id="131210349711",  # already stamped
    )

    mp_data_from_mp = {
        "id": "131210349711",
        "payer_id": "",
        "payer_email": "",
        "preapproval_plan_id": "mp_plan_193",
        "status": "authorized",
    }

    def fake_fetch(preapproval_id):
        return mp_data_from_mp, _FakeCred(org)

    with patch(
        "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
        side_effect=fake_fetch,
    ):
        result = process_athlete_subscription_webhook({"id": "131210349711", "status": "authorized"})

    # Fast path hit directly (sub already has mp_preapproval_id)
    assert result["outcome"] in ("updated", "noop")
    assert result["preapproval_id"] == "131210349711"

    sub.refresh_from_db()
    assert sub.status == "active"


# ── T5: AthleteSubscription visible in Django Admin ──────────────────────────

class TestAthleteSubscriptionAdmin(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "admin_193", "admin_193@test.com", "adminpass"
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    @override_settings(
        STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
    )
    def test_athlete_subscription_admin_200(self):
        resp = self.client.get("/admin/core/athletesubscription/")
        self.assertEqual(resp.status_code, 200)
