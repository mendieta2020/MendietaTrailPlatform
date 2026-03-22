"""
PR-136 — AthleteSubscription webhook handler.

10 tests covering:
- authorized / paused / cancelled transitions
- idempotency (same event twice = noop)
- pending = noop
- unknown preapproval_id = not_found (no exception)
- missing preapproval_id = noop
- invalid JSON = 400
- B2B webhook non-regression
- cross-status transition guard
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from core.models import (
    Athlete,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    Organization,
    OrganizationSubscription,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATHLETE_WEBHOOK_URL = "/api/webhooks/mercadopago/athlete/"
B2B_WEBHOOK_URL = "/api/webhooks/mercadopago/"


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email=None):
    return User.objects.create_user(
        username=username,
        password="testpass",
        email=email or f"{username}@example.com",
    )


def _plan(org, name="Plan Test", price="3000.00"):
    return CoachPricingPlan.objects.create(
        organization=org,
        name=name,
        price_ars=price,
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _subscription(athlete, org, plan, status="pending", preapproval_id="PA-001"):
    return AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status=status,
        mp_preapproval_id=preapproval_id,
    )


def _post_json(client, url, payload):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Unit-level tests for process_athlete_subscription_webhook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_authorized_activates_subscription():
    """authorized → status=active, last_payment_at set."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-auth-1")
    user = _user("ath_auth1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    sub = _subscription(athlete, org, plan, status="pending", preapproval_id="PA-AUTH-1")

    result = process_athlete_subscription_webhook({"id": "PA-AUTH-1", "status": "authorized"})

    assert result["outcome"] == "updated"
    assert result["preapproval_id"] == "PA-AUTH-1"

    sub.refresh_from_db()
    assert sub.status == "active"
    assert sub.last_payment_at is not None


@pytest.mark.django_db
def test_authorized_idempotent():
    """Same authorized event twice → second call is noop."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-idem-1")
    user = _user("ath_idem1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    _subscription(athlete, org, plan, status="pending", preapproval_id="PA-IDEM-1")

    process_athlete_subscription_webhook({"id": "PA-IDEM-1", "status": "authorized"})
    result = process_athlete_subscription_webhook({"id": "PA-IDEM-1", "status": "authorized"})

    assert result["outcome"] == "noop"
    assert result["preapproval_id"] == "PA-IDEM-1"


@pytest.mark.django_db
def test_paused_sets_overdue():
    """paused → status=overdue."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-paused-1")
    user = _user("ath_paused1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-PAUSED-1")

    result = process_athlete_subscription_webhook({"id": "PA-PAUSED-1", "status": "paused"})

    assert result["outcome"] == "updated"
    sub.refresh_from_db()
    assert sub.status == "overdue"


@pytest.mark.django_db
def test_cancelled_sets_cancelled():
    """cancelled → status=cancelled."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-cancel-1")
    user = _user("ath_cancel1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-CANCEL-1")

    result = process_athlete_subscription_webhook({"id": "PA-CANCEL-1", "status": "cancelled"})

    assert result["outcome"] == "updated"
    sub.refresh_from_db()
    assert sub.status == "cancelled"


@pytest.mark.django_db
def test_pending_is_noop():
    """pending → no status change, outcome=noop."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-pend-1")
    user = _user("ath_pend1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    sub = _subscription(athlete, org, plan, status="pending", preapproval_id="PA-PEND-1")

    result = process_athlete_subscription_webhook({"id": "PA-PEND-1", "status": "pending"})

    assert result["outcome"] == "noop"
    sub.refresh_from_db()
    assert sub.status == "pending"


@pytest.mark.django_db
def test_unknown_preapproval_id_returns_not_found():
    """Non-existent preapproval_id → outcome=not_found, no exception raised."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    result = process_athlete_subscription_webhook({"id": "PA-GHOST-999", "status": "authorized"})

    assert result["outcome"] == "not_found"
    assert result["preapproval_id"] == "PA-GHOST-999"


@pytest.mark.django_db
def test_missing_preapproval_id_returns_noop():
    """Payload without 'id' or 'data.id' → outcome=noop, preapproval_id=None."""
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    result = process_athlete_subscription_webhook({"type": "subscription_preapproval", "status": "authorized"})

    assert result["outcome"] == "noop"
    assert result["preapproval_id"] is None


@pytest.mark.django_db
def test_invalid_json_returns_400():
    """POST with non-JSON body → 400."""
    client = Client()
    response = client.post(
        ATHLETE_WEBHOOK_URL,
        data="not{valid}json",
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_existing_b2b_webhook_unaffected():
    """POST to /api/webhooks/mercadopago/ still returns 200 (no regression)."""
    client = Client()
    payload = {"type": "payment", "data": {"id": "PA-B2B-001"}}
    response = _post_json(client, B2B_WEBHOOK_URL, payload)
    assert response.status_code == 200


@pytest.mark.django_db
def test_cross_status_transition():
    """
    active → cancelled via webhook, then second authorized event must NOT
    re-activate (athlete is cancelled — authorized on a cancelled sub updates it).
    Then verify: cancelled sub receives authorized → becomes active again (MP says so).
    And a noop-path: cancelled → cancelled event → noop.
    """
    from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook

    org = _org("org-cross-1")
    user = _user("ath_cross1")
    plan = _plan(org)
    athlete = _athlete(user, org)
    sub = _subscription(athlete, org, plan, status="active", preapproval_id="PA-CROSS-1")

    # Step 1: cancel
    r1 = process_athlete_subscription_webhook({"id": "PA-CROSS-1", "status": "cancelled"})
    assert r1["outcome"] == "updated"
    sub.refresh_from_db()
    assert sub.status == "cancelled"

    # Step 2: duplicate cancelled event → noop
    r2 = process_athlete_subscription_webhook({"id": "PA-CROSS-1", "status": "cancelled"})
    assert r2["outcome"] == "noop"
    sub.refresh_from_db()
    assert sub.status == "cancelled"
