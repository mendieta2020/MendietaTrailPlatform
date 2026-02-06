from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Alumno
from core.strava_oauth_views import can_start_strava_oauth


class StravaOAuthPermissionTests(TestCase):
    def test_coach_cannot_start_strava_oauth(self):
        coach = User.objects.create_user(username="coach_strava", password="x")
        self.assertFalse(can_start_strava_oauth(coach))

    def test_athlete_can_start_strava_oauth(self):
        coach = User.objects.create_user(username="coach_owner", password="x")
        athlete_user = User.objects.create_user(username="athlete_strava", password="x")
        Alumno.objects.create(
            entrenador=coach,
            usuario=athlete_user,
            nombre="Ana",
            apellido="Runner",
            email="ana@test.com",
        )
        self.assertTrue(can_start_strava_oauth(athlete_user))
