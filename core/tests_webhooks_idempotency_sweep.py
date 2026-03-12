"""
PR-125 — Webhook Idempotency Test Sweep
========================================
Law 5 (CONSTITUTION.md): external events must be safe to process multiple times.
Duplicates must be noop (not double-create).

13 tests · 5 groups
"""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ExternalIdentity, StravaWebhookEvent

WEBHOOK_URL = "/webhooks/strava/"


def _activity_payload(**overrides):
    base = {
        "object_type": "activity",
        "aspect_type": "create",
        "object_id": 7001,
        "owner_id": 8001,
        "subscription_id": 1,
        "event_time": 1700000001,
    }
    base.update(overrides)
    return base


# ==============================================================================
#  Group 1 — Input validation (400 paths)
# ==============================================================================

@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestInputValidation(TestCase):
    """Malformed payloads must be rejected with HTTP 400 before any DB write."""

    def setUp(self):
        self.client = APIClient()

    def test_invalid_json_returns_400(self):
        """Non-JSON body → 400 immediately, no event created."""
        res = self.client.post(
            WEBHOOK_URL,
            data="not-json{{{",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_missing_required_fields_returns_400(self):
        """Payload without owner_id → 400, no event created."""
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 7001,
            # owner_id intentionally omitted
            "subscription_id": 1,
        }
        res = self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_incorrect_field_types_returns_400(self):
        """Non-integer object_id → 400, no event created."""
        payload = _activity_payload(object_id="not-an-int", owner_id="also-bad")
        res = self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)


# ==============================================================================
#  Group 2 — Discard paths (non-activity + delete events)
# ==============================================================================

@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestDiscardPaths(TestCase):
    """Events outside the happy-path must be DISCARDED and never enqueued."""

    def setUp(self):
        self.client = APIClient()

    def test_non_activity_event_is_discarded_and_not_enqueued(self):
        """object_type=athlete → event stored as DISCARDED, Celery task NOT called."""
        payload = _activity_payload(object_type="athlete")
        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        delay_mock.assert_not_called()
        event = StravaWebhookEvent.objects.get()
        self.assertEqual(event.status, StravaWebhookEvent.Status.DISCARDED)

    def test_delete_event_is_discarded_and_not_enqueued(self):
        """aspect_type=delete → event stored as DISCARDED, Celery task NOT called."""
        payload = _activity_payload(aspect_type="delete")
        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        delay_mock.assert_not_called()
        event = StravaWebhookEvent.objects.get()
        self.assertEqual(event.status, StravaWebhookEvent.Status.DISCARDED)


# ==============================================================================
#  Group 3 — Duplicate / requeue semantics
# ==============================================================================

@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestDuplicateRequeue(TestCase):
    """
    Idempotency guarantee: the same event_uid arriving twice must not create
    a second DB row.  Requeue behaviour depends on the existing event's status.
    """

    def setUp(self):
        self.client = APIClient()

    def _post(self, payload=None):
        payload = payload or _activity_payload()
        return self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_duplicate_increments_duplicate_count(self):
        """Second identical POST: still one event row, duplicate_count == 1."""
        payload = _activity_payload()
        with patch("core.webhooks.process_strava_event.delay"):
            self._post(payload)
            res2 = self._post(payload)

        self.assertEqual(res2.status_code, 200)
        self.assertEqual(StravaWebhookEvent.objects.count(), 1)
        event = StravaWebhookEvent.objects.get()
        self.assertEqual(event.duplicate_count, 1)

    def test_failed_event_is_requeued_on_duplicate(self):
        """Duplicate arriving for a FAILED event must re-enqueue it (process_strava_event.delay called)."""
        payload = _activity_payload()

        with patch("core.webhooks.process_strava_event.delay"):
            self._post(payload)

        # Force event into FAILED state
        StravaWebhookEvent.objects.update(status=StravaWebhookEvent.Status.FAILED)

        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self._post(payload)

        self.assertEqual(res.status_code, 200)
        delay_mock.assert_called_once()
        event = StravaWebhookEvent.objects.get()
        self.assertEqual(event.status, StravaWebhookEvent.Status.QUEUED)

    def test_processed_event_is_noop_on_duplicate(self):
        """Duplicate arriving for a PROCESSED event must NOT re-enqueue."""
        payload = _activity_payload()

        with patch("core.webhooks.process_strava_event.delay"):
            self._post(payload)

        # Force event into PROCESSED state (terminal)
        StravaWebhookEvent.objects.update(status=StravaWebhookEvent.Status.PROCESSED)

        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self._post(payload)

        self.assertEqual(res.status_code, 200)
        delay_mock.assert_not_called()


# ==============================================================================
#  Group 4 — ExternalIdentity seeding
# ==============================================================================

@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestExternalIdentitySeeding(TestCase):
    """
    A fresh webhook event must seed ExternalIdentity so that the athlete can be
    linked later without losing the event.  Seeding failures must not block the
    webhook response.
    """

    def setUp(self):
        self.client = APIClient()

    def test_new_event_creates_external_identity(self):
        """First activity event creates an UNLINKED ExternalIdentity for the owner."""
        payload = _activity_payload(owner_id=9001)
        with patch("core.webhooks.process_strava_event.delay"):
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        identity = ExternalIdentity.objects.get(provider="strava", external_user_id="9001")
        self.assertEqual(identity.status, ExternalIdentity.Status.UNLINKED)

    def test_external_identity_seed_failure_does_not_block_webhook(self):
        """If ExternalIdentity.get_or_create raises, webhook still returns 200 and enqueues."""
        payload = _activity_payload(owner_id=9002)
        with (
            patch(
                "core.webhooks.ExternalIdentity.objects.get_or_create",
                side_effect=Exception("DB blip"),
            ),
            patch("core.webhooks.process_strava_event.delay") as delay_mock,
        ):
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        # Task was still enqueued despite the identity failure
        delay_mock.assert_called_once()


# ==============================================================================
#  Group 5 — Persistence failures → 500 so Strava retries
# ==============================================================================

@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestPersistenceFailures(TestCase):
    """
    If the DB is unavailable when writing the webhook event, the endpoint must
    return HTTP 500 so that Strava retries delivery later.
    """

    def setUp(self):
        self.client = APIClient()

    def test_generic_db_error_on_get_or_create_returns_500(self):
        """get_or_create raises a generic exception (DB down) → 500, no event row."""
        payload = _activity_payload()
        with patch(
            "core.webhooks.StravaWebhookEvent.objects.get_or_create",
            side_effect=Exception("connection refused"),
        ):
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 500)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_integrity_error_with_no_recovery_returns_500(self):
        """IntegrityError + subsequent filter returns nothing → 500 (unrecoverable race)."""
        from django.db import IntegrityError as DjIntegrityError

        payload = _activity_payload()

        # Simulate the race: get_or_create raises IntegrityError but the filter
        # also returns nothing (extremely rare, but must not hang).
        with (
            patch(
                "core.webhooks.StravaWebhookEvent.objects.get_or_create",
                side_effect=DjIntegrityError("unique violation"),
            ),
            patch(
                "core.webhooks.StravaWebhookEvent.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 500)

    def test_integrity_error_with_recovery_returns_200(self):
        """IntegrityError + existing event recovered via filter → 200 (duplicate path)."""
        from django.db import IntegrityError as DjIntegrityError

        payload = _activity_payload()

        # Pre-create a PROCESSED event to simulate the recovered duplicate
        existing = StravaWebhookEvent.objects.create(
            provider="strava",
            event_uid="recovered-uid-001",
            object_type="activity",
            object_id=7001,
            aspect_type="create",
            owner_id=8001,
            subscription_id=1,
            event_time=1700000001,
            payload_raw=payload,
            status=StravaWebhookEvent.Status.PROCESSED,
        )

        with (
            patch(
                "core.webhooks.StravaWebhookEvent.objects.get_or_create",
                side_effect=DjIntegrityError("unique violation"),
            ),
            patch(
                "core.webhooks.StravaWebhookEvent.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=existing)),
            ),
            patch("core.webhooks.process_strava_event.delay") as delay_mock,
        ):
            res = self.client.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        # PROCESSED is terminal → noop duplicate, still 200
        self.assertEqual(res.status_code, 200)
        delay_mock.assert_not_called()
