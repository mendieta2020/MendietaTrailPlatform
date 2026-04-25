from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Alumno

User = get_user_model()

_CREDENTIALS = [
    ("owner@test.com", "test1234"),
    ("coach@test.com", "test1234"),
    ("atleta1@test.com", "test1234"),
    ("atleta2@test.com", "test1234"),
]

# /api/token/ uses email + password (EmailTokenObtainPairSerializer)


@override_settings(DEBUG=True)
class SeedTestUsersCommandTest(TestCase):
    def setUp(self):
        call_command("seed_test_users", verbosity=0)

    def test_idempotent(self):
        call_command("seed_test_users", verbosity=0)
        count = User.objects.filter(username__endswith="@test.com").count()
        self.assertEqual(count, 4)

    def test_superuser(self):
        user = User.objects.get(username="owner@test.com")
        self.assertTrue(user.is_superuser)

    def test_coach_relation(self):
        coach = User.objects.get(username="coach@test.com")
        atleta1 = User.objects.get(username="atleta1@test.com")
        alumno = Alumno.objects.get(usuario=atleta1)
        self.assertEqual(alumno.entrenador, coach)

    @override_settings(DEBUG=False)  # method-level override wins over class-level DEBUG=True
    def test_production_guard(self):
        with self.assertRaises(CommandError):
            call_command("seed_test_users", verbosity=0)

    def test_all_users_can_authenticate(self):
        client = APIClient()
        for email, password in _CREDENTIALS:
            response = client.post(
                "/api/token/",
                {"email": email, "password": password},
                format="json",
            )
            self.assertEqual(
                response.status_code,
                200,
                msg=f"Auth failed for {email}: status={response.status_code}",
            )
