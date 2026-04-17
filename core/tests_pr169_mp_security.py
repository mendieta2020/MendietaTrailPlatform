"""
PR-169 — MP Security & Reliability Bundle.

13 tests covering:
1.  create_preapproval_plan includes notification_url
2.  patch_mp_notification_urls command updates existing plans
3.  patch_mp_notification_urls command is idempotent (safe rerun)
4.  Webhook signature valid → 200
5.  Webhook signature invalid → 401
6.  No MERCADOPAGO_WEBHOOK_SECRET configured → passthrough (dev mode)
7.  overdue webhook creates InternalMessages for both owner and athlete
8.  overdue webhook does NOT cancel the subscription
9.  daily_mp_reconciliation fixes pending sub when MP returns authorized
10. daily_mp_reconciliation logs orphan when authorized preapproval has no sub
11. pre_charge_notification sends message 3 days before renewal
12. pre_charge_notification is idempotent (no duplicate messages)
13. pre_charge_notification skips cancelled subscriptions
"""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch, call

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.utils import timezone

from core.models import (
    Athlete,
    AthleteSubscription,
    CoachPricingPlan,
    InternalMessage,
    Membership,
    Organization,
    OrgOAuthCredential,
)

User = get_user_model()

ATHLETE_WEBHOOK_URL = "/api/webhooks/mercadopago/athlete/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email=None):
    return User.objects.create_user(
        username=username,
        password="testpass",
        email=email or f"{username}@example.com",
    )


def _plan(org, name="Plan Test", price="3000.00", mp_plan_id=None):
    return CoachPricingPlan.objects.create(
        organization=org, name=name, price_ars=price, mp_plan_id=mp_plan_id,
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _membership(user, org, role="owner"):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _subscription(athlete, org, plan, status="pending", preapproval_id=None, next_payment_at=None):
    return AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status=status,
        mp_preapproval_id=preapproval_id,
        next_payment_at=next_payment_at,
    )


def _cred(org, access_token="tok_test"):
    return OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago", access_token=access_token,
    )


def _post_json(client, url, payload, headers=None):
    kwargs = {"content_type": "application/json"}
    if headers:
        kwargs.update(headers)
    return client.post(url, data=json.dumps(payload), **kwargs)


def _make_mp_signature(secret: str, data_id: str, request_id: str, ts: str) -> str:
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    return hmac.new(
        secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# ===========================================================================
# Feature 1 — notification_url in create_preapproval_plan
# ===========================================================================

@pytest.mark.django_db
def test_create_plan_includes_notification_url(settings):
    """create_preapproval_plan() must include notification_url pointing at our endpoint."""
    from integrations.mercadopago.subscriptions import create_preapproval_plan

    settings.BACKEND_URL = "https://api.example.com"
    settings.TESTING = True

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.json.return_value = {"id": "plan-001"}

    with patch("integrations.mercadopago.subscriptions._requests.post", return_value=fake_response) as mock_post:
        create_preapproval_plan(
            access_token="tok",
            name="Plan Elite",
            price_ars=5000,
            back_url="https://app.example.com/back",
        )

    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
    assert "notification_url" in payload
    assert payload["notification_url"] == "https://api.example.com/api/webhooks/mercadopago/athlete/"


@pytest.mark.django_db
def test_patch_command_updates_existing_plans(settings):
    """patch_mp_notification_urls command calls PUT preapproval_plan for each plan."""
    from django.core.management import call_command
    from io import StringIO

    settings.BACKEND_URL = "https://api.example.com"

    org = _org("patch-org-1")
    _plan(org, name="Elite", mp_plan_id="mp-plan-001")
    _cred(org, access_token="tok_patch")

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.json.return_value = {"id": "mp-plan-001"}

    with patch("integrations.mercadopago.subscriptions._requests.put", return_value=fake_response) as mock_put:
        out = StringIO()
        call_command("patch_mp_notification_urls", stdout=out)

    assert mock_put.called
    call_body = mock_put.call_args[1]["json"]
    assert "notification_url" in call_body
    assert "api.example.com" in call_body["notification_url"]
    assert "patched" in out.getvalue()


@pytest.mark.django_db
def test_patch_command_idempotent(settings):
    """Running patch_mp_notification_urls twice calls PUT the same number of times each run."""
    from django.core.management import call_command
    from io import StringIO

    settings.BACKEND_URL = "https://api.example.com"

    org = _org("patch-org-2")
    _plan(org, name="Starter", mp_plan_id="mp-plan-002")
    _cred(org, access_token="tok_idem")

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.json.return_value = {"id": "mp-plan-002"}

    with patch("integrations.mercadopago.subscriptions._requests.put", return_value=fake_response) as mock_put:
        call_command("patch_mp_notification_urls", stdout=StringIO())
        call_command("patch_mp_notification_urls", stdout=StringIO())

    # Both runs must call PUT exactly once each (1 plan × 2 runs = 2 total calls)
    assert mock_put.call_count == 2


# ===========================================================================
# Feature 2 — Webhook signature verification
# ===========================================================================

@pytest.mark.django_db
def test_webhook_signature_valid_accepted(settings):
    """Valid HMAC signature → webhook processed (200)."""
    secret = "test-webhook-secret-abc123"
    settings.MERCADOPAGO_WEBHOOK_SECRET = secret

    org = _org("sig-org-valid")
    owner_user = _user("sig_owner_valid")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan Sig Valid")
    athlete_user = _user("sig_athlete_valid")
    athlete = _athlete(athlete_user, org)
    _subscription(athlete, org, plan, status="pending", preapproval_id="PA-SIG-VALID")

    data_id = "PA-SIG-VALID"
    request_id = "req-001"
    ts = "1700000000"
    sig_hash = _make_mp_signature(secret, data_id, request_id, ts)

    client = Client()
    response = client.post(
        f"{ATHLETE_WEBHOOK_URL}?data.id={data_id}",
        data=json.dumps({"id": "PA-SIG-VALID", "status": "authorized"}),
        content_type="application/json",
        HTTP_X_SIGNATURE=f"ts={ts},v1={sig_hash}",
        HTTP_X_REQUEST_ID=request_id,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_webhook_signature_invalid_rejected_401(settings):
    """Tampered HMAC signature → 401 rejected."""
    settings.MERCADOPAGO_WEBHOOK_SECRET = "correct-secret"

    client = Client()
    response = client.post(
        f"{ATHLETE_WEBHOOK_URL}?data.id=PA-FAKE",
        data=json.dumps({"id": "PA-FAKE", "status": "authorized"}),
        content_type="application/json",
        HTTP_X_SIGNATURE="ts=1700000000,v1=deadbeefdeadbeefdeadbeef",
        HTTP_X_REQUEST_ID="req-bad",
    )
    assert response.status_code == 401
    data = response.json()
    assert "Invalid signature" in data.get("detail", "")


@pytest.mark.django_db
def test_webhook_no_signature_config_allows_passthrough(settings):
    """No MERCADOPAGO_WEBHOOK_SECRET configured → 200 passthrough (dev mode)."""
    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    # No matching subscription → expect not_found (200 still returned)
    client = Client()
    response = client.post(
        ATHLETE_WEBHOOK_URL,
        data=json.dumps({"id": "PA-NOCONFIG", "status": "authorized"}),
        content_type="application/json",
    )
    assert response.status_code == 200


# ===========================================================================
# Feature 4 — Failed payment (overdue) handling
# ===========================================================================

@pytest.mark.django_db
def test_webhook_overdue_creates_messages_both_parties(settings):
    """overdue webhook creates InternalMessages for both the owner and the athlete."""
    settings.MERCADOPAGO_WEBHOOK_SECRET = ""  # dev passthrough

    org = _org("overdue-org-1")
    owner_user = _user("overdue_owner1")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan Overdue 1")
    athlete_user = _user("overdue_athlete1")
    athlete = _athlete(athlete_user, org)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-OVERDUE-1")

    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
    result = process_athlete_subscription_webhook({"id": "PA-OVERDUE-1", "status": "overdue"})

    assert result["outcome"] == "updated"
    sub.refresh_from_db()
    assert sub.status == "overdue"

    msgs = InternalMessage.objects.filter(organization=org, alert_type="payment_failed")
    assert msgs.count() == 2

    recipients = set(msgs.values_list("recipient_id", flat=True))
    assert owner_user.id in recipients
    assert athlete_user.id in recipients


@pytest.mark.django_db
def test_webhook_overdue_does_not_cancel_sub(settings):
    """overdue webhook must NOT cancel the subscription — status stays overdue."""
    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("overdue-org-2")
    owner_user = _user("overdue_owner2")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan Overdue 2")
    athlete_user = _user("overdue_athlete2")
    athlete = _athlete(athlete_user, org)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-OVERDUE-2")

    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
    process_athlete_subscription_webhook({"id": "PA-OVERDUE-2", "status": "overdue"})

    sub.refresh_from_db()
    assert sub.status == "overdue"
    assert sub.status != "cancelled"


# ===========================================================================
# Feature 3 — Daily reconciliation
# ===========================================================================

@pytest.mark.django_db
def test_daily_reconciliation_fixes_pending_with_authorized_mp(settings):
    """daily_mp_reconciliation: pending sub that MP says authorized → reconciled to active."""
    from io import StringIO
    from django.core.management import call_command

    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("reconcile-org-1")
    owner_user = _user("rec_owner1")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan Rec 1")
    athlete_user = _user("rec_athlete1")
    athlete = _athlete(athlete_user, org)
    sub = _subscription(athlete, org, plan, status="pending", preapproval_id="PA-REC-1")
    _cred(org, access_token="tok_rec1")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"id": "PA-REC-1", "status": "authorized"}

    with patch("requests.get", return_value=fake_resp):
        with patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[]):
            out = StringIO()
            call_command("daily_mp_reconciliation", stdout=out)

    sub.refresh_from_db()
    assert sub.status == "active"
    assert "reconciled" in out.getvalue()


@pytest.mark.django_db
def test_daily_reconciliation_logs_orphans(settings):
    """daily_mp_reconciliation: authorized MP preapproval with no matching sub → logged as orphan."""
    from io import StringIO
    from django.core.management import call_command
    import logging

    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("reconcile-org-2")
    owner_user = _user("rec_owner2")
    _membership(owner_user, org, "owner")
    _plan(org, name="Plan Rec 2", mp_plan_id="mp-rec-plan-2")
    _cred(org, access_token="tok_rec2")
    # No AthleteSubscription with the orphan preapproval_id

    orphan_preapproval = {"id": "PA-ORPHAN-1", "status": "authorized"}

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: {})):
        with patch("integrations.mercadopago.subscriptions.search_preapprovals", return_value=[orphan_preapproval]):
            out = StringIO()
            call_command("daily_mp_reconciliation", stdout=out)

    assert "ORPHAN" in out.getvalue() or "orphan" in out.getvalue().lower()


# ===========================================================================
# Feature 5 — Pre-charge notifications
# ===========================================================================

@pytest.mark.django_db
def test_pre_charge_notification_sends_3_days_before(settings):
    """pre_charge_notifications sends InternalMessage when next_payment_at is 3.5 days away."""
    from io import StringIO
    from django.core.management import call_command

    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("precharge-org-1")
    owner_user = _user("pc_owner1")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan PC 1", price="4000.00")
    athlete_user = _user("pc_athlete1")
    athlete = _athlete(athlete_user, org)

    next_payment = timezone.now() + timedelta(days=3, hours=12)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-PC-1", next_payment_at=next_payment)

    out = StringIO()
    call_command("pre_charge_notifications", stdout=out)

    sub.refresh_from_db()
    assert sub.last_pre_charge_notification_sent_at is not None

    msgs = InternalMessage.objects.filter(
        organization=org,
        recipient=athlete_user,
        alert_type="pre_charge_reminder",
    )
    assert msgs.count() == 1
    assert "Plan PC 1" in msgs.first().content
    assert "sent=1" in out.getvalue()


@pytest.mark.django_db
def test_pre_charge_idempotent_no_duplicate_messages(settings):
    """Running pre_charge_notifications twice within 24h does not send duplicate messages."""
    from io import StringIO
    from django.core.management import call_command

    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("precharge-org-2")
    owner_user = _user("pc_owner2")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan PC 2", price="3500.00")
    athlete_user = _user("pc_athlete2")
    athlete = _athlete(athlete_user, org)

    next_payment = timezone.now() + timedelta(days=3, hours=6)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-PC-2", next_payment_at=next_payment)

    call_command("pre_charge_notifications", stdout=StringIO())
    call_command("pre_charge_notifications", stdout=StringIO())

    msgs = InternalMessage.objects.filter(
        organization=org,
        recipient=athlete_user,
        alert_type="pre_charge_reminder",
    )
    assert msgs.count() == 1  # second run was skipped


@pytest.mark.django_db
def test_pre_charge_skips_cancelled_subs(settings):
    """pre_charge_notifications must not send messages to cancelled subscriptions."""
    from io import StringIO
    from django.core.management import call_command

    settings.MERCADOPAGO_WEBHOOK_SECRET = ""

    org = _org("precharge-org-3")
    owner_user = _user("pc_owner3")
    _membership(owner_user, org, "owner")
    plan = _plan(org, name="Plan PC 3")
    athlete_user = _user("pc_athlete3")
    athlete = _athlete(athlete_user, org)

    next_payment = timezone.now() + timedelta(days=3, hours=6)
    _subscription(athlete, org, plan, status="cancelled", preapproval_id="PA-PC-3", next_payment_at=next_payment)

    out = StringIO()
    call_command("pre_charge_notifications", stdout=out)

    msgs = InternalMessage.objects.filter(
        organization=org,
        recipient=athlete_user,
        alert_type="pre_charge_reminder",
    )
    assert msgs.count() == 0
    # cancelled sub is excluded by status="active" filter — command finds nothing to send
    assert "renewing" in out.getvalue() or "sent=0" in out.getvalue()
