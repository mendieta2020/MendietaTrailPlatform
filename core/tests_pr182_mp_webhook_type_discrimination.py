"""
core/tests_pr182_mp_webhook_type_discrimination.py

PR-182 Bug #40: MercadoPago webhook type discrimination.

Validates that process_athlete_subscription_webhook correctly handles the
three webhook types MP sends via the ?type= query string:
  - subscription_preapproval: payload.data.id IS preapproval_id (fast path)
  - payment: payload.data.id is payment_id; resolve via MP API
  - subscription_authorized_payment: same resolution path as payment
  - no type (None): backward-compat fallback → treated as preapproval_id

Six tests:
  T1 — subscription_preapproval fast-path (regression guard)
  T2 — payment type resolves preapproval from metadata.preapproval_id
  T3 — payment type resolves from point_of_interaction.transaction_data.subscription_id
  T4 — payment type with no linked preapproval → noop
  T5 — subscription_authorized_payment resolves and updates
  T6 — no type (None) falls back to preapproval_id lookup (backward compat)

All tests use an empty test DB so AthleteSubscription.DoesNotExist is raised naturally.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase


class MPWebhookTypeDiscriminationTests(TestCase):

    def _call(self, payload, webhook_type):
        from integrations.mercadopago.athlete_webhook import process_athlete_subscription_webhook
        return process_athlete_subscription_webhook(payload, webhook_type=webhook_type)

    # ── T1: subscription_preapproval uses direct preapproval_id ──────────────

    def test_preapproval_webhook_fast_path(self):
        """type=subscription_preapproval → preapproval_id used directly (no MP API call)."""
        payload = {"data": {"id": "PREAPPROVAL-001"}}

        with patch(
            "integrations.mercadopago.athlete_webhook._resolve_preapproval_from_payment"
        ) as mock_resolve, patch(
            "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
            return_value=(None, None),
        ):
            result = self._call(payload, webhook_type="subscription_preapproval")
            mock_resolve.assert_not_called()
            # Empty DB → not_found, but preapproval_id must be the original value
            self.assertEqual(result["preapproval_id"], "PREAPPROVAL-001")

    # ── T2: payment type resolves from metadata.preapproval_id ──────────────

    def test_payment_webhook_resolves_from_metadata(self):
        """type=payment → calls _resolve_preapproval_from_payment; uses metadata result."""
        payload = {"data": {"id": "PAYMENT-001"}}

        with patch(
            "integrations.mercadopago.athlete_webhook._resolve_preapproval_from_payment",
            return_value="PREAPPROVAL-FROM-META",
        ) as mock_resolve, patch(
            "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
            return_value=(None, None),
        ):
            result = self._call(payload, webhook_type="payment")
            mock_resolve.assert_called_once_with("PAYMENT-001")
            # resolved id must be forwarded, regardless of final DB outcome
            self.assertEqual(result["preapproval_id"], "PREAPPROVAL-FROM-META")

    # ── T3: payment type resolves from point_of_interaction ─────────────────

    def test_payment_webhook_resolves_from_point_of_interaction(self):
        """_resolve_preapproval_from_payment checks point_of_interaction.transaction_data."""
        mock_payment = {
            "metadata": {},
            "point_of_interaction": {
                "transaction_data": {"subscription_id": "PREAPPROVAL-FROM-POI"}
            },
        }
        with patch(
            "integrations.mercadopago.subscriptions._requests.get"
        ) as mock_get, patch(
            "core.models.OrgOAuthCredential.objects.filter"
        ) as mock_creds:
            mock_cred = MagicMock()
            mock_cred.access_token = "tok"
            mock_creds.return_value = [mock_cred]
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_payment
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            from integrations.mercadopago.athlete_webhook import _resolve_preapproval_from_payment
            result = _resolve_preapproval_from_payment("PAYMENT-002")
            self.assertEqual(result, "PREAPPROVAL-FROM-POI")

    # ── T4: payment type with no linked preapproval → noop ──────────────────

    def test_payment_webhook_no_preapproval_linked_returns_noop(self):
        """type=payment; MP API returns no preapproval link → outcome=noop."""
        payload = {"data": {"id": "PAYMENT-ORPHAN"}}

        with patch(
            "integrations.mercadopago.athlete_webhook._resolve_preapproval_from_payment",
            return_value=None,
        ):
            result = self._call(payload, webhook_type="payment")
            self.assertEqual(result["outcome"], "noop")
            self.assertIsNone(result["preapproval_id"])

    # ── T5: subscription_authorized_payment resolves and updates ────────────

    def test_authorized_payment_webhook_resolves_and_updates(self):
        """type=subscription_authorized_payment follows same path as type=payment."""
        payload = {"data": {"id": "AUTH-PAYMENT-001"}}

        with patch(
            "integrations.mercadopago.athlete_webhook._resolve_preapproval_from_payment",
            return_value="PREAPPROVAL-AUTH",
        ) as mock_resolve, patch(
            "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
            return_value=(None, None),
        ):
            result = self._call(payload, webhook_type="subscription_authorized_payment")
            mock_resolve.assert_called_once_with("AUTH-PAYMENT-001")
            self.assertEqual(result["preapproval_id"], "PREAPPROVAL-AUTH")

    # ── T6: no type falls back to preapproval_id (backward compat) ──────────

    def test_webhook_no_type_falls_back_to_preapproval(self):
        """type=None → treated as subscription_preapproval; resolve_from_payment not called."""
        payload = {"data": {"id": "PREAPPROVAL-LEGACY"}}

        with patch(
            "integrations.mercadopago.athlete_webhook._resolve_preapproval_from_payment"
        ) as mock_resolve, patch(
            "integrations.mercadopago.athlete_webhook._fetch_preapproval_with_any_coach_token",
            return_value=(None, None),
        ):
            result = self._call(payload, webhook_type=None)
            mock_resolve.assert_not_called()
            self.assertEqual(result["preapproval_id"], "PREAPPROVAL-LEGACY")
