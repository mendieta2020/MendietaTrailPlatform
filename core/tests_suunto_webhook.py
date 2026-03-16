"""
PR-136 — Protective tests for the Suunto webhook endpoint.

Covers:
  - Happy path: auth + payload → event created + task enqueued
  - Duplicate noop (Ley 5 idempotency)
  - Auth failures: missing header, wrong key, unconfigured key
  - Payload failures: invalid JSON, missing required fields
  - HTTP method guard: GET → 405
  - Unlinked identity → LINK_REQUIRED (event stored, task NOT enqueued)
  - Linked identity → task enqueued with correct alumno_id
  - Deterministic event_uid (same input → same uid; different input → different uid)
  - Requeue of FAILED event on duplicate arrival
"""
import json
import hashlib
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import StravaWebhookEvent, ExternalIdentity

User = get_user_model()

SUUNTO_KEY = "test-suunto-key-abc123"
WEBHOOK_URL = "/webhooks/suunto/"


def _auth_headers(key=SUUNTO_KEY):
    """Build the Suunto APIM auth header dict for APIClient."""
    return {"HTTP_OCP_APIM_SUBSCRIPTION_KEY": key}


def _payload(username="athlete_user", workout_key="wk-001", event_type="workout_create"):
    return {
        "username": username,
        "workoutid": workout_key,
        "event_type": event_type,
    }


def _post(client, payload=None, headers=None, content_type="application/json"):
    if payload is None:
        payload = _payload()
    if headers is None:
        headers = _auth_headers()
    body = json.dumps(payload)
    return client.post(WEBHOOK_URL, body, content_type=content_type, **headers)


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookHappyPath(TestCase):
    """Happy path: valid auth + valid payload → event created + task enqueued."""

    def setUp(self):
        self.client = APIClient()
        # Create a coach (Entrenador) and athlete (Alumno) for linked-identity tests.
        from core.models import Alumno
        self.coach = User.objects.create_user(
            username="coach_pr136", password="x", email="coach136@test.com"
        )
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Athlete PR136",
            apellido="Test",
        )
        self.identity = ExternalIdentity.objects.create(
            provider="suunto",
            external_user_id="athlete_user",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_post_valid_payload_creates_event_and_enqueues(self, delay_mock):
        """HTTP 200, one StravaWebhookEvent with provider=suunto, task enqueued."""
        response = _post(self.client)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StravaWebhookEvent.objects.filter(provider="suunto").count(), 1
        )
        event = StravaWebhookEvent.objects.get(provider="suunto")
        self.assertEqual(event.status, StravaWebhookEvent.Status.QUEUED)
        self.assertEqual(event.object_type, "workout")
        delay_mock.assert_called_once_with(
            alumno_id=self.alumno.pk, external_workout_id="wk-001"
        )

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_workoutkey_field_name_also_accepted(self, delay_mock):
        """Payload using 'workoutKey' (camelCase) is accepted."""
        payload = {"username": "athlete_user", "workoutKey": "wk-camel"}
        body = json.dumps(payload)
        response = self.client.post(
            WEBHOOK_URL, body, content_type="application/json", **_auth_headers()
        )
        self.assertEqual(response.status_code, 200)
        delay_mock.assert_called_once()


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookIdempotency(TestCase):
    """Ley 5 — duplicate events must be noop."""

    def setUp(self):
        self.client = APIClient()
        from core.models import Alumno
        self.coach = User.objects.create_user(
            username="coach_idem", password="x", email="coach_idem@test.com"
        )
        self.alumno = Alumno.objects.create(
            entrenador=self.coach, nombre="Idem", apellido="Athlete"
        )
        ExternalIdentity.objects.create(
            provider="suunto",
            external_user_id="dup_user",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_duplicate_payload_is_noop(self, delay_mock):
        """Sending the same payload twice: second call increments duplicate_count, no re-enqueue."""
        payload = _payload(username="dup_user", workout_key="wk-dup")

        r1 = _post(self.client, payload)
        r2 = _post(self.client, payload)

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            StravaWebhookEvent.objects.filter(provider="suunto").count(), 1
        )
        event = StravaWebhookEvent.objects.get(provider="suunto")
        self.assertEqual(event.duplicate_count, 1)
        # Task enqueued only once (first call).
        self.assertEqual(delay_mock.call_count, 1)

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_idempotency_requeue_on_failed_event(self, delay_mock):
        """A FAILED event that receives a duplicate should be re-queued."""
        from integrations.suunto.webhook import compute_suunto_event_uid
        parsed = {"username": "dup_user", "workout_key": "wk-retry"}
        uid = compute_suunto_event_uid(parsed)

        # Pre-seed a FAILED event.
        StravaWebhookEvent.objects.create(
            event_uid=uid,
            provider="suunto",
            object_type="workout",
            object_id=0,
            aspect_type="workout_create",
            owner_id=0,
            payload_raw={**parsed, "_resolved_alumno_id": self.alumno.pk},
            status=StravaWebhookEvent.Status.FAILED,
        )

        payload = {"username": "dup_user", "workoutid": "wk-retry"}
        r = _post(self.client, payload)

        self.assertEqual(r.status_code, 200)
        event = StravaWebhookEvent.objects.get(event_uid=uid)
        self.assertEqual(event.status, StravaWebhookEvent.Status.QUEUED)
        delay_mock.assert_called_once()


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookAuthGuard(TestCase):
    """Auth failures must return 403 without creating any DB records."""

    def setUp(self):
        self.client = APIClient()

    def test_missing_auth_header_returns_403(self):
        """No Ocp-Apim-Subscription-Key header → 403."""
        response = self.client.post(
            WEBHOOK_URL,
            json.dumps(_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_wrong_auth_header_returns_403(self):
        """Wrong key value → 403."""
        response = _post(self.client, headers=_auth_headers(key="wrong-key"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    @override_settings(SUUNTO_SUBSCRIPTION_KEY="")
    def test_missing_subscription_key_setting_returns_403(self):
        """If SUUNTO_SUBSCRIPTION_KEY is empty in settings → fail-closed 403."""
        response = _post(self.client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookPayloadValidation(TestCase):
    """Invalid payloads must return 400 without creating any DB records."""

    def setUp(self):
        self.client = APIClient()

    def test_invalid_json_returns_400(self):
        """Non-JSON body → 400."""
        response = self.client.post(
            WEBHOOK_URL,
            "not-json",
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_missing_username_returns_400(self):
        """Payload without username → 400."""
        payload = {"workoutid": "wk-001"}
        response = _post(self.client, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)

    def test_missing_workout_key_returns_400(self):
        """Payload without workoutid/workoutKey → 400."""
        payload = {"username": "athlete_x"}
        response = _post(self.client, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StravaWebhookEvent.objects.count(), 0)


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookHttpMethods(TestCase):
    """Only POST is accepted."""

    def setUp(self):
        self.client = APIClient()

    def test_get_returns_405(self):
        """GET /webhooks/suunto/ → 405."""
        response = self.client.get(WEBHOOK_URL, **_auth_headers())
        self.assertEqual(response.status_code, 405)


@override_settings(SUUNTO_SUBSCRIPTION_KEY=SUUNTO_KEY)
class TestSuuntoWebhookIdentityFlow(TestCase):
    """ExternalIdentity linking and LINK_REQUIRED flow."""

    def setUp(self):
        self.client = APIClient()
        from core.models import Alumno
        self.coach = User.objects.create_user(
            username="coach_link", password="x", email="link@test.com"
        )
        self.alumno = Alumno.objects.create(
            entrenador=self.coach, nombre="Link", apellido="Athlete"
        )

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_unlinked_identity_marks_event_link_required(self, delay_mock):
        """Unknown username: event stored as LINK_REQUIRED, task NOT enqueued."""
        payload = _payload(username="unknown_athlete", workout_key="wk-new")
        response = _post(self.client, payload)

        self.assertEqual(response.status_code, 200)
        event = StravaWebhookEvent.objects.get(provider="suunto")
        self.assertEqual(event.status, StravaWebhookEvent.Status.LINK_REQUIRED)
        delay_mock.assert_not_called()
        # ExternalIdentity seeded as UNLINKED.
        identity = ExternalIdentity.objects.get(
            provider="suunto", external_user_id="unknown_athlete"
        )
        self.assertEqual(identity.status, ExternalIdentity.Status.UNLINKED)

    @patch("integrations.suunto.tasks.ingest_workout.delay")
    def test_linked_identity_resolves_alumno_and_enqueues(self, delay_mock):
        """Known + linked username: task enqueued with correct alumno_id."""
        ExternalIdentity.objects.create(
            provider="suunto",
            external_user_id="linked_athlete",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )
        payload = _payload(username="linked_athlete", workout_key="wk-linked")
        response = _post(self.client, payload)

        self.assertEqual(response.status_code, 200)
        event = StravaWebhookEvent.objects.get(provider="suunto")
        self.assertEqual(event.status, StravaWebhookEvent.Status.QUEUED)
        delay_mock.assert_called_once_with(
            alumno_id=self.alumno.pk, external_workout_id="wk-linked"
        )


class TestSuuntoEventUid(TestCase):
    """Unit tests for compute_suunto_event_uid — no DB needed."""

    def test_event_uid_deterministic(self):
        """Same input always produces the same uid."""
        from integrations.suunto.webhook import compute_suunto_event_uid

        parsed = {"username": "u1", "workout_key": "wk-x", "event_type": "workout_create"}
        uid1 = compute_suunto_event_uid(parsed)
        uid2 = compute_suunto_event_uid(parsed)
        self.assertEqual(uid1, uid2)

    def test_different_payloads_produce_different_uids(self):
        """Different workout_key → different uid."""
        from integrations.suunto.webhook import compute_suunto_event_uid

        p1 = {"username": "u1", "workout_key": "wk-a", "event_type": "workout_create"}
        p2 = {"username": "u1", "workout_key": "wk-b", "event_type": "workout_create"}
        self.assertNotEqual(
            compute_suunto_event_uid(p1), compute_suunto_event_uid(p2)
        )

    def test_event_type_excluded_from_uid(self):
        """create and update for the same workout hash to the same uid (deduplication)."""
        from integrations.suunto.webhook import compute_suunto_event_uid

        p_create = {"username": "u1", "workout_key": "wk-z", "event_type": "workout_create"}
        p_update = {"username": "u1", "workout_key": "wk-z", "event_type": "workout_update"}
        self.assertEqual(
            compute_suunto_event_uid(p_create), compute_suunto_event_uid(p_update)
        )

    def test_uid_max_length_respected(self):
        """uid must fit in StravaWebhookEvent.event_uid (max_length=80)."""
        from integrations.suunto.webhook import compute_suunto_event_uid

        uid = compute_suunto_event_uid({"username": "u", "workout_key": "k", "event_type": "x"})
        self.assertLessEqual(len(uid), 80)

    def test_suunto_uid_differs_from_strava_uid(self):
        """UID includes 'suunto' prefix so it can never collide with Strava events."""
        from integrations.suunto.webhook import compute_suunto_event_uid

        uid = compute_suunto_event_uid({"username": "u", "workout_key": "k", "event_type": "x"})
        # Manually compute a Strava-style uid to confirm no collision is possible.
        strava_like = hashlib.sha256(
            json.dumps(
                {"provider": "strava", "username": "u", "workout_key": "k"},
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()[:80]
        self.assertNotEqual(uid, strava_like)
