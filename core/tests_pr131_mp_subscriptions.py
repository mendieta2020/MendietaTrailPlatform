"""
PR-131 — MercadoPago Subscriptions Foundation
Tests: trial logic, webhook processing, webhook endpoint.
"""
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import Organization, OrganizationSubscription


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    """Create an Organization (triggers auto_create_subscription_with_trial signal)."""
    org = Organization.objects.create(name="TestOrg131", slug="test-org-131")
    return org


@pytest.fixture
def sub(org):
    return OrganizationSubscription.objects.get(organization=org)


# ---------------------------------------------------------------------------
# Trial auto-creation (signal)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTrialAutoCreation:
    def test_trial_auto_created_on_org_creation(self, sub):
        """New org has trial_ends_at set in the future."""
        assert sub.trial_ends_at is not None
        assert sub.trial_ends_at > timezone.now()

    def test_trial_plan_is_pro(self, sub):
        """New org has plan='pro' during trial."""
        assert sub.plan == OrganizationSubscription.Plan.PRO

    def test_trial_has_plan_pro_returns_true(self, sub):
        """has_plan('pro') is True within trial period."""
        assert sub.has_plan("pro") is True

    def test_trial_has_plan_enterprise_returns_false(self, sub):
        """has_plan('enterprise') is False during Pro trial (Pro rank < Enterprise)."""
        assert sub.has_plan("enterprise") is False

    def test_trial_expired_has_plan_returns_false(self, sub):
        """has_plan('pro') is False when trial_ends_at is in the past."""
        sub.trial_ends_at = timezone.now() - timedelta(days=1)
        sub.is_active = False
        sub.save()
        assert sub.has_plan("pro") is False

    def test_is_in_trial_true(self, sub):
        """is_in_trial() returns True within trial."""
        assert sub.is_in_trial() is True

    def test_is_in_trial_false(self, sub):
        """is_in_trial() returns False when trial has expired."""
        sub.trial_ends_at = timezone.now() - timedelta(seconds=1)
        sub.save()
        assert sub.is_in_trial() is False


# ---------------------------------------------------------------------------
# Webhook processing (integration layer)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMercadoPagoWebhookProcessing:
    def _make_sub_with_preapproval(self, org, preapproval_id):
        sub = OrganizationSubscription.objects.get(organization=org)
        sub.mp_preapproval_id = preapproval_id
        sub.save(update_fields=["mp_preapproval_id"])
        return sub

    def test_webhook_authorized_activates_subscription(self, org):
        """payload authorized -> is_active=True."""
        from integrations.mercadopago.webhook import process_subscription_webhook
        preapproval_id = "PA-authorized-001"
        sub = self._make_sub_with_preapproval(org, preapproval_id)
        sub.is_active = False
        sub.save(update_fields=["is_active"])

        payload = {"type": "subscription_preapproval", "data": {"id": preapproval_id}}
        with patch("integrations.mercadopago.webhook.mp_get", return_value={"status": "authorized"}):
            process_subscription_webhook(payload)

        sub.refresh_from_db()
        assert sub.is_active is True

    def test_webhook_cancelled_deactivates_subscription(self, org):
        """payload cancelled -> is_active=False."""
        from integrations.mercadopago.webhook import process_subscription_webhook
        preapproval_id = "PA-cancelled-001"
        sub = self._make_sub_with_preapproval(org, preapproval_id)
        sub.is_active = True
        sub.save(update_fields=["is_active"])

        payload = {"type": "subscription_preapproval", "data": {"id": preapproval_id}}
        with patch("integrations.mercadopago.webhook.mp_get", return_value={"status": "cancelled"}):
            process_subscription_webhook(payload)

        sub.refresh_from_db()
        assert sub.is_active is False

    def test_webhook_unknown_preapproval_ignored(self, org):
        """Unknown preapproval_id logs warning but raises no exception."""
        from integrations.mercadopago.webhook import process_subscription_webhook
        payload = {"type": "subscription_preapproval", "data": {"id": "PA-unknown-999"}}
        with patch("integrations.mercadopago.webhook.mp_get", return_value={"status": "authorized"}):
            # Should not raise
            process_subscription_webhook(payload)

    def test_webhook_wrong_type_ignored(self, org):
        """Type != subscription_preapproval -> no DB changes."""
        from integrations.mercadopago.webhook import process_subscription_webhook
        preapproval_id = "PA-wrong-type-001"
        sub = self._make_sub_with_preapproval(org, preapproval_id)
        original_active = sub.is_active

        payload = {"type": "payment", "data": {"id": preapproval_id}}
        process_subscription_webhook(payload)

        sub.refresh_from_db()
        assert sub.is_active == original_active


# ---------------------------------------------------------------------------
# Webhook endpoint (HTTP layer)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMercadoPagoWebhookEndpoint:
    def test_webhook_endpoint_200(self, org, client):
        """POST /api/webhooks/mercadopago/ with valid payload -> 200."""
        payload = {"type": "payment", "data": {"id": "PA-001"}}
        response = client.post(
            "/api/webhooks/mercadopago/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_webhook_endpoint_400(self, org, client):
        """POST /api/webhooks/mercadopago/ with invalid JSON -> 400."""
        response = client.post(
            "/api/webhooks/mercadopago/",
            data="not-valid-json{{{",
            content_type="application/json",
        )
        assert response.status_code == 400
