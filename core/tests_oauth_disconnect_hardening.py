"""
PR-126 — OAuth Critical Path Test Hardening
=============================================
Laws 2, 6 (CONSTITUTION.md):
- Every critical path must have protective tests
- Never log tokens/secrets/PII

10 tests covering untested branches in IntegrationDisconnectView and IntegrationStartView.
Zero production code changes.
"""
import requests
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.integration_models import OAuthIntegrationStatus
from core.integration_views import IntegrationStartView
from core.models import Alumno, ExternalIdentity, Membership, OAuthCredential, Organization

User = get_user_model()


# ==============================================================================
# GRUPO 1: IntegrationDisconnectView — Branches no testeados (6 tests)
# ==============================================================================


class DisconnectUnsupportedProviderTests(TestCase):
    """Test 1: DELETE with provider != 'strava' → 400 unsupported."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_d1", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_d1", password="x")
        Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="D1",
        )

    def test_disconnect_unsupported_provider_returns_400(self):
        """
        GIVEN: Authenticated user with Alumno profile.
        WHEN:  DELETE /api/integrations/garmin/disconnect/ (provider != "strava").
        THEN:  HTTP 400, body {"error": "unsupported"}.
        """
        self.client.force_login(self.athlete_user)
        res = self.client.delete("/api/integrations/garmin/disconnect/")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "unsupported")


class DisconnectUserWithoutAlumnoTests(TestCase):
    """Test 2: User with no Alumno row → 204 idempotent (Alumno.DoesNotExist branch)."""

    def test_disconnect_user_without_alumno_returns_204(self):
        """
        GIVEN: Authenticated user without Alumno profile.
        WHEN:  DELETE /api/integrations/strava/disconnect/.
        THEN:  HTTP 204 — nothing to disconnect, idempotent.
        """
        user = User.objects.create_user(username="bare_user_d2", password="x")
        self.client.force_login(user)
        res = self.client.delete("/api/integrations/strava/disconnect/")
        self.assertEqual(res.status_code, 204)


class DisconnectRevokeTimeoutTests(TestCase):
    """Test 3: requests.Timeout during Strava revoke → local purge still happens, 204."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_d3", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_d3", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="Test",
            apellido="D3",
            email="d3@test.com",
            # No strava_athlete_id: avoids post_save signal auto-creating ExternalIdentity
        )
        OAuthCredential.objects.create(
            alumno=self.alumno,
            provider="strava",
            external_user_id="77001",
            access_token="tok_to_purge",
            refresh_token="ref_to_purge",
            expires_at=timezone.now() + timezone.timedelta(hours=6),
        )
        ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="77001",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            athlete_id="77001",
            status=OAuthIntegrationStatus.Status.CONNECTED,
        )

    def test_disconnect_revoke_timeout_still_purges_locally(self):
        """
        GIVEN: Full seed with OAuthCredential, ExternalIdentity (LINKED), OAuthIntegrationStatus (CONNECTED).
        WHEN:  DELETE with Strava revoke endpoint raising requests.exceptions.Timeout.
        THEN:  HTTP 204; OAuthCredential gone; ExternalIdentity DISABLED; OIS DISCONNECTED.
        """
        self.client.force_login(self.athlete_user)
        with patch("requests.post", side_effect=requests.exceptions.Timeout("connect timeout")):
            res = self.client.delete("/api/integrations/strava/disconnect/")

        self.assertEqual(res.status_code, 204)
        self.assertFalse(
            OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").exists()
        )
        identity = ExternalIdentity.objects.get(alumno=self.alumno, provider="strava")
        self.assertEqual(identity.status, ExternalIdentity.Status.DISABLED)
        ois = OAuthIntegrationStatus.objects.get(alumno=self.alumno, provider="strava")
        self.assertFalse(ois.connected)
        self.assertEqual(ois.status, OAuthIntegrationStatus.Status.DISCONNECTED)


class DisconnectRevokeHttp500Tests(TestCase):
    """Test 4: Strava revoke returns HTTP 500 → local purge still happens, 204."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_d4", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_d4", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="D4",
            # No strava_athlete_id: avoids post_save signal auto-creating ExternalIdentity
        )
        OAuthCredential.objects.create(
            alumno=self.alumno,
            provider="strava",
            external_user_id="77002",
            access_token="tok_d4",
            refresh_token="ref_d4",
            expires_at=timezone.now() + timezone.timedelta(hours=6),
        )
        ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="77002",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            athlete_id="77002",
            status=OAuthIntegrationStatus.Status.CONNECTED,
        )

    def test_disconnect_revoke_http_500_still_purges_locally(self):
        """
        GIVEN: Full seed.
        WHEN:  DELETE with Strava revoke returning HTTP 500.
        THEN:  HTTP 204; local purge completed identically to Test 3.
        """
        self.client.force_login(self.athlete_user)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("requests.post", return_value=mock_resp):
            res = self.client.delete("/api/integrations/strava/disconnect/")

        self.assertEqual(res.status_code, 204)
        self.assertFalse(
            OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").exists()
        )
        identity = ExternalIdentity.objects.get(alumno=self.alumno, provider="strava")
        self.assertEqual(identity.status, ExternalIdentity.Status.DISABLED)
        ois = OAuthIntegrationStatus.objects.get(alumno=self.alumno, provider="strava")
        self.assertFalse(ois.connected)
        self.assertEqual(ois.status, OAuthIntegrationStatus.Status.DISCONNECTED)


class DisconnectNoTokenForRevokeTests(TestCase):
    """Test 5: ExternalIdentity(LINKED) but no OAuthCredential → REVOKE_SKIPPED_NO_TOKEN, 204."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_d5", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_d5", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="D5",
            # No strava_athlete_id: avoids post_save signal auto-creating ExternalIdentity
        )
        # ExternalIdentity LINKED but NO OAuthCredential and NO SocialAccount/SocialToken.
        ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="77003",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            athlete_id="77003",
            status=OAuthIntegrationStatus.Status.CONNECTED,
        )

    def test_disconnect_no_token_for_revoke_still_completes(self):
        """
        GIVEN: ExternalIdentity LINKED, no OAuthCredential, no SocialAccount.
        WHEN:  DELETE /api/integrations/strava/disconnect/.
        THEN:  HTTP 204; ExternalIdentity DISABLED (revoke_reason_code=REVOKE_SKIPPED_NO_TOKEN).
        """
        self.client.force_login(self.athlete_user)
        res = self.client.delete("/api/integrations/strava/disconnect/")
        self.assertEqual(res.status_code, 204)
        identity = ExternalIdentity.objects.get(alumno=self.alumno, provider="strava")
        self.assertEqual(identity.status, ExternalIdentity.Status.DISABLED)


class DisconnectDoneLogContractTests(TestCase):
    """Test 6: strava.disconnect.done log record carries all required structured fields; no token leak."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_d6", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_d6", password="x")
        self.org = Organization.objects.create(name="DisconnectTestOrg", slug="disconnect-test-org")
        Membership.objects.create(user=self.athlete_user, organization=self.org, role="athlete", is_active=True)
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="D6",
            # No strava_athlete_id: avoids post_save signal auto-creating ExternalIdentity
        )
        OAuthCredential.objects.create(
            alumno=self.alumno,
            provider="strava",
            external_user_id="77004",
            access_token="tok_canary_126",
            refresh_token="ref_d6",
            expires_at=timezone.now() + timezone.timedelta(hours=6),
        )
        ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="77004",
            alumno=self.alumno,
            status=ExternalIdentity.Status.LINKED,
        )
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            athlete_id="77004",
            status=OAuthIntegrationStatus.Status.CONNECTED,
        )

    def test_disconnect_done_log_has_required_fields(self):
        """
        GIVEN: Full seed with access_token="tok_canary_126".
        WHEN:  DELETE with revoke mocked OK (200).
        THEN:  strava.disconnect.done record has all required structured fields;
               the canary token value never appears in any log record.
        """
        self.client.force_login(self.athlete_user)
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.post", return_value=mock_resp):
            with self.assertLogs("core.integration_views", level="INFO") as cm:
                res = self.client.delete("/api/integrations/strava/disconnect/")

        self.assertEqual(res.status_code, 204)

        done_record = next(
            (r for r in cm.records if r.getMessage() == "strava.disconnect.done"),
            None,
        )
        self.assertIsNotNone(done_record, "Expected log record with message 'strava.disconnect.done'")

        required_fields = [
            "event_name", "user_id", "organization_id", "provider",
            "outcome", "reason_code", "revoke_reason_code",
            "deleted_credentials", "deleted_tokens", "deleted_accounts",
            "disabled_identities",
        ]
        for field in required_fields:
            self.assertTrue(
                hasattr(done_record, field),
                f"Log record missing required structured field: '{field}'",
            )

        self.assertEqual(done_record.event_name, "strava.disconnect.done")
        self.assertEqual(done_record.provider, "strava")
        self.assertEqual(done_record.outcome, "OK")
        self.assertEqual(done_record.reason_code, "DISCONNECT_OK")
        self.assertEqual(done_record.revoke_reason_code, "REVOKE_OK")
        self.assertIsInstance(done_record.user_id, int)
        self.assertIsInstance(done_record.organization_id, int)
        self.assertGreaterEqual(done_record.deleted_credentials, 0)
        self.assertGreaterEqual(done_record.deleted_tokens, 0)
        self.assertGreaterEqual(done_record.deleted_accounts, 0)
        self.assertGreaterEqual(done_record.disabled_identities, 0)

        # Law 6: canary token must never appear in any log record message.
        for record in cm.records:
            self.assertNotIn(
                "tok_canary_126",
                record.getMessage(),
                "access_token must never appear in log output (Law 6 violation)",
            )


# ==============================================================================
# GRUPO 2: IntegrationStartView — Branches no testeados (4 tests)
# ==============================================================================


class StartDisabledProviderTests(TestCase):
    """Test 7: Registered-but-disabled provider (garmin) → 422 provider_disabled."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_s7", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_s7", password="x")
        Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="S7",
        )

    def test_start_disabled_provider_returns_422(self):
        """
        GIVEN: Authenticated user with Alumno profile.
        WHEN:  POST /api/integrations/garmin/start (garmin enabled=False in registry).
        THEN:  HTTP 422, {"error": "provider_disabled", "provider": "garmin"}.
        """
        self.client.force_login(self.athlete_user)
        url = reverse("integration_start", kwargs={"provider": "garmin"})
        res = self.client.post(url)
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.data["error"], "provider_disabled")
        self.assertEqual(res.data["provider"], "garmin")


class StartMissingCallbackUriTests(TestCase):
    """Test 8: _get_callback_uri returns None → 500 server_misconfigured."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_s8", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_s8", password="x")
        Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="S8",
        )

    def test_start_missing_callback_uri_returns_500(self):
        """
        GIVEN: Authenticated user with Alumno; _get_callback_uri mocked to return None.
        WHEN:  POST /api/integrations/strava/start.
        THEN:  HTTP 500, {"error": "server_misconfigured"}.
        """
        self.client.force_login(self.athlete_user)
        url = reverse("integration_start", kwargs={"provider": "strava"})
        with patch.object(IntegrationStartView, "_get_callback_uri", return_value=None):
            res = self.client.post(url)
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.data["error"], "server_misconfigured")


class StartCacheNotSharedTests(TestCase):
    """Test 9: generate_oauth_state raises RuntimeError('Shared cache required') → 503."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_s9", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_s9", password="x")
        Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="S9",
        )

    def test_start_cache_not_shared_returns_503(self):
        """
        GIVEN: Authenticated user with Alumno; generate_oauth_state raises RuntimeError('Shared cache required').
        WHEN:  POST /api/integrations/strava/start.
        THEN:  HTTP 503, {"error": "cache_not_shared", "reason_code": "CACHE_NOT_SHARED"}.
        """
        self.client.force_login(self.athlete_user)
        url = reverse("integration_start", kwargs={"provider": "strava"})
        with (
            patch(
                "core.integration_views.generate_oauth_state",
                side_effect=RuntimeError("Shared cache required for OAuth state"),
            ),
            patch.object(IntegrationStartView, "_validate_provider_config", return_value=True),
        ):
            res = self.client.post(url)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.data["error"], "cache_not_shared")
        self.assertEqual(res.data["reason_code"], "CACHE_NOT_SHARED")


class StartUnexpectedRuntimeErrorTests(TestCase):
    """Test 10: generate_oauth_state raises generic RuntimeError → propagates (500)."""

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_s10", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_s10", password="x")
        Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="S10",
        )

    def test_start_unexpected_runtime_error_propagates(self):
        """
        GIVEN: Authenticated user with Alumno; generate_oauth_state raises RuntimeError("Something unexpected").
        WHEN:  POST /api/integrations/strava/start.
        THEN:  The exception propagates (DRF re-raises non-APIException; Django test client re-raises).
        """
        self.client.force_login(self.athlete_user)
        url = reverse("integration_start", kwargs={"provider": "strava"})
        with (
            patch(
                "core.integration_views.generate_oauth_state",
                side_effect=RuntimeError("Something unexpected"),
            ),
            patch.object(IntegrationStartView, "_validate_provider_config", return_value=True),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(url)
