import time
from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount, SocialToken
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.models import Alumno
from core.strava_integration_views import build_strava_oauth_state


@override_settings(
    FRONTEND_BASE_URL="http://frontend.test",
    STRAVA_CLIENT_ID="client-id",
    STRAVA_CLIENT_SECRET="client-secret",
    STRAVA_OAUTH_STATE_TTL_SECONDS=600,
)
class StravaOAuthApiTests(APITestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def _create_athlete(self, username="athlete"):
        user = self.user_model.objects.create_user(username=username, password="pass")
        alumno = Alumno.objects.create(usuario=user, nombre="Ana", apellido="Test")
        return user, alumno

    def test_start_requires_auth(self):
        response = self.client.post("/api/integrations/strava/start")
        self.assertEqual(response.status_code, 401)

    def test_start_for_non_athlete_forbidden(self):
        coach = self.user_model.objects.create_user(username="coach", password="pass")
        self.client.force_authenticate(user=coach)
        response = self.client.post("/api/integrations/strava/start")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"detail": "Solo atletas pueden conectar Strava."})

    def test_start_for_athlete_returns_oauth_url(self):
        user, _alumno = self._create_athlete()
        self.client.force_authenticate(user=user)
        response = self.client.post("/api/integrations/strava/start")
        self.assertEqual(response.status_code, 200)
        oauth_url = response.data.get("oauth_url", "")
        self.assertIn("https://www.strava.com/oauth/authorize", oauth_url)
        self.assertIn("state=", oauth_url)

    def test_callback_invalid_state_redirects_error(self):
        response = self.client.get("/api/integrations/strava/callback?state=bad&code=abc")
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "http://frontend.test/athlete/integrations?strava=error&reason=invalid_state",
            response["Location"],
        )

    def test_callback_valid_state_persists_token_and_redirects(self):
        user, alumno = self._create_athlete(username="athlete2")
        state = build_strava_oauth_state(user_id=user.id)
        token_payload = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": int(time.time()) + 3600,
            "athlete": {"id": 12345, "firstname": "Ana"},
        }

        with patch("core.strava_integration_views.Client.exchange_code_for_token", return_value=token_payload):
            response = self.client.get(
                f"/api/integrations/strava/callback?state={state}&code=valid-code"
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "http://frontend.test/athlete/integrations?strava=connected",
            response["Location"],
        )
        self.assertTrue(
            SocialAccount.objects.filter(user=user, provider="strava", uid="12345").exists()
        )
        token = SocialToken.objects.filter(account__user=user, account__provider="strava").first()
        self.assertIsNotNone(token)
        self.assertEqual(token.token, "access-token")
        self.assertEqual(token.token_secret, "refresh-token")
        alumno.refresh_from_db()
        self.assertEqual(alumno.strava_athlete_id, "12345")
