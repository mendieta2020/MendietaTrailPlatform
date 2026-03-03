import json
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from core.models import Alumno
from core.integration_models import OAuthIntegrationStatus

User = get_user_model()

class PR19StravaStateTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_pr19", password="x")
        self.user = User.objects.create_user(username="athlete_pr19", password="x")
        
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.user,
            nombre="Ana",
            apellido="Pr19",
            email="ana_pr19@test.com",
            strava_athlete_id="9999",
        )
        
        # Setup SocialApp
        self.social_app = SocialApp.objects.create(
            provider="strava",
            name="Strava PR19",
            client_id="123",
            secret="abc"
        )
        
        self.client = APIClient()

    def _setup_connected_state(self):
        account = SocialAccount.objects.create(
            user=self.user,
            provider="strava",
            uid="9999"
        )
        SocialToken.objects.create(
            app=self.social_app,
            account=account,
            token="access_123",
            token_secret="refresh_123"
        )
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            status=OAuthIntegrationStatus.Status.CONNECTED,
            athlete_id="9999"
        )

    def test_status_endpoint_requires_authentication(self):
        url = reverse("provider_status", kwargs={"provider": "strava"})
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_disconnect_endpoint_requires_authentication(self):
        url = reverse("integration_disconnect", kwargs={"provider": "strava"})
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deleting_social_account_makes_status_unlinked_despite_oauth_status(self):
        """
        P0: Single source of truth. If SocialAccount is missing, status must be unlinked,
        even if OAuthIntegrationStatus claims it is connected.
        """
        self._setup_connected_state()
        self.client.force_authenticate(user=self.user)
        
        # Verify initially connected
        url = reverse("provider_status", kwargs={"provider": "strava"})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["connected"])
        
        # Delete SocialAccount (simulate data anomaly or manual deletion)
        SocialAccount.objects.all().delete()
        
        # Status MUST be unlinked now
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["connected"])
        self.assertEqual(res.data["status"], "unlinked")
        self.assertEqual(res.data["athlete_id"], "")

    def test_disconnect_endpoint_sets_connected_false_idempotent(self):
        """
        Disconnecting must remove SocialAccount and clear connection state idempotently.
        """
        self._setup_connected_state()
        self.client.force_authenticate(user=self.user)
        
        url = reverse("integration_disconnect", kwargs={"provider": "strava"})
        
        # First call
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 204)  # PR21: now returns 204 No Content
        
        # Verify SocialAccount gone
        self.assertEqual(SocialAccount.objects.count(), 0)
        
        # Verify Alumno strava_athlete_id is None
        self.alumno.refresh_from_db()
        self.assertIsNone(self.alumno.strava_athlete_id)
        
        # Verify OAuthIntegrationStatus is DISCONNECTED
        integ = OAuthIntegrationStatus.objects.get(alumno=self.alumno, provider="strava")
        self.assertFalse(integ.connected)
        self.assertEqual(integ.status, OAuthIntegrationStatus.Status.DISCONNECTED)
        
        # Second call (idempotent)
        res2 = self.client.delete(url)
        self.assertEqual(res2.status_code, 204)  # PR21: idempotent, must not error

    def test_status_endpoint_returns_valid_data(self):
        self._setup_connected_state()
        self.client.force_authenticate(user=self.user)
        
        url = reverse("provider_status", kwargs={"provider": "strava"})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["connected"])
        self.assertEqual(res.data["athlete_id"], "9999")
        self.assertEqual(res.data["status"], "connected")
