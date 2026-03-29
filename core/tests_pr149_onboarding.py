"""
PR-149 — Athlete registration + onboarding tests.
Covers: RegisterView, GoogleAuthView, OnboardingCompleteView.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteAvailability,
    AthleteGoal,
    AthleteInvitation,
    AthleteProfile,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    Organization,
    OrgOAuthCredential,
    RaceEvent,
)

User = get_user_model()

FAKE_MP_DATA = {
    "id": "preaproval_onboarding_123",
    "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?id=onb123",
    "status": "pending",
}

DEFAULT_AVAILABILITY = [
    {"day_of_week": i, "is_available": i < 5, "reason": "" if i < 5 else "Descanso", "preferred_time": ""}
    for i in range(7)
]


def _make_org(name="Mendieta Trail"):
    slug = name.lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:4]}"
    return Organization.objects.create(name=name, slug=slug)


def _make_user(email=None, password="TestPass123!"):
    email = email or f"user_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password=password)


def _make_plan(org, name="Classic", price_ars="38000.00", mp_plan_id="mp_plan_classic"):
    return CoachPricingPlan.objects.create(
        organization=org, name=name, price_ars=price_ars,
        mp_plan_id=mp_plan_id, is_active=True,
    )


def _make_invitation(org, plan, email="athlete@test.com", days=30):
    return AthleteInvitation.objects.create(
        organization=org, coach_plan=plan, email=email,
        expires_at=timezone.now() + timedelta(days=days),
    )


def _make_mp_cred(org):
    return OrgOAuthCredential.objects.create(
        organization=org, provider="mercadopago",
        access_token="mp_access_token", refresh_token="mp_refresh_token",
        provider_user_id="mp_user_123",
    )


# ==============================================================================
# RegisterView Tests
# ==============================================================================

class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/register/"

    def test_register_success(self):
        resp = self.client.post(self.url, {
            "email": "new_athlete@test.com",
            "password": "StrongPass123!",
            "first_name": "Juan",
            "last_name": "Pérez",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertTrue(User.objects.filter(email="new_athlete@test.com").exists())

    def test_register_duplicate_email(self):
        _make_user(email="existing@test.com")
        resp = self.client.post(self.url, {
            "email": "existing@test.com",
            "password": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        resp = self.client.post(self.url, {
            "email": "weak@test.com",
            "password": "123",
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_email(self):
        resp = self.client.post(self.url, {"password": "StrongPass123!"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# GoogleAuthView Tests
# ==============================================================================

class GoogleAuthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/google/"

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_google_auth_new_user(self, mock_verify):
        mock_verify.return_value = {
            "email": "google_user@gmail.com",
            "given_name": "Maria",
            "family_name": "Lopez",
            "sub": "google_id_123",
        }
        resp = self.client.post(self.url, {"credential": "fake_google_token"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        user = User.objects.get(email="google_user@gmail.com")
        self.assertEqual(user.first_name, "Maria")

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_google_auth_existing_user(self, mock_verify):
        existing = _make_user(email="existing_google@gmail.com")
        mock_verify.return_value = {
            "email": "existing_google@gmail.com",
            "given_name": "Existing",
            "family_name": "User",
        }
        resp = self.client.post(self.url, {"credential": "fake_google_token"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Should not create a duplicate
        self.assertEqual(User.objects.filter(email="existing_google@gmail.com").count(), 1)

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_google_auth_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Invalid token")
        resp = self.client.post(self.url, {"credential": "bad_token"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# OnboardingCompleteView Tests
# ==============================================================================

class OnboardingCompleteViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/onboarding/complete/"
        self.org = _make_org()
        self.plan = _make_plan(self.org)
        self.mp_cred = _make_mp_cred(self.org)
        self.user = _make_user(email="athlete_onboarding@test.com")
        self.invite = _make_invitation(self.org, self.plan, email=self.user.email)

    def _payload(self, **overrides):
        data = {
            "invitation_token": str(self.invite.token),
            "first_name": "Carlos",
            "last_name": "Gutierrez",
            "birth_date": "1990-05-15",
            "weight_kg": 72.5,
            "height_cm": 175.0,
            "phone_number": "+5491112345678",
            "availability": DEFAULT_AVAILABILITY,
        }
        data.update(overrides)
        return data

    @patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval", return_value=FAKE_MP_DATA)
    def test_full_onboarding_success(self, mock_mp):
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, f"Response: {resp.data}")
        self.assertIn("redirect_url", resp.data)

        # Verify all records created
        self.assertTrue(Membership.objects.filter(
            user=self.user, organization=self.org, role="athlete",
        ).exists())

        athlete = Athlete.objects.get(user=self.user, organization=self.org)
        self.assertEqual(athlete.phone_number, "+5491112345678")

        profile = AthleteProfile.objects.get(athlete=athlete)
        self.assertEqual(profile.weight_kg, 72.5)
        self.assertEqual(profile.height_cm, 175.0)
        self.assertEqual(profile.birth_date.isoformat(), "1990-05-15")

        # 7 availability entries
        self.assertEqual(
            AthleteAvailability.objects.filter(athlete=athlete).count(), 7,
        )

        # Invitation marked accepted
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.status, AthleteInvitation.Status.ACCEPTED)

        # AthleteSubscription created
        self.assertTrue(AthleteSubscription.objects.filter(
            athlete=athlete, coach_plan=self.plan,
        ).exists())

    @patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval", return_value=FAKE_MP_DATA)
    def test_onboarding_with_goal(self, mock_mp):
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._payload(
            goal={
                "race_name": "Patagonia Run 100K",
                "race_date": "2026-12-05",
                "distance_km": 100.0,
                "elevation_gain_m": 5500.0,
                "priority": "A",
            },
        ), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        athlete = Athlete.objects.get(user=self.user, organization=self.org)
        goal = AthleteGoal.objects.get(athlete=athlete)
        self.assertEqual(goal.title, "Patagonia Run 100K")
        self.assertEqual(goal.priority, "A")

        race = RaceEvent.objects.get(organization=self.org, name="Patagonia Run 100K")
        self.assertEqual(race.distance_km, 100.0)

    def test_onboarding_invalid_token(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            self.url,
            self._payload(invitation_token=str(uuid.uuid4())),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_onboarding_expired_invitation(self):
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save(update_fields=["expires_at"])
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval", return_value=FAKE_MP_DATA)
    def test_onboarding_idempotent(self, mock_mp):
        # Create membership first to simulate already-onboarded user
        Membership.objects.create(user=self.user, organization=self.org, role="athlete")
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get("already_member"))

    def test_onboarding_unauthenticated(self):
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval", return_value=FAKE_MP_DATA)
    def test_availability_creates_7_entries(self, mock_mp):
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        athlete = Athlete.objects.get(user=self.user, organization=self.org)
        avail = AthleteAvailability.objects.filter(athlete=athlete)
        self.assertEqual(avail.count(), 7)
        # Weekdays available, weekends not
        self.assertTrue(avail.get(day_of_week=0).is_available)
        self.assertFalse(avail.get(day_of_week=5).is_available)

    @patch("integrations.mercadopago.subscriptions.create_coach_athlete_preapproval", return_value=FAKE_MP_DATA)
    def test_org_scoping(self, mock_mp):
        """Athlete is scoped to the invitation's organization."""
        self.client.force_authenticate(self.user)
        self.client.post(self.url, self._payload(), format="json")

        athlete = Athlete.objects.get(user=self.user)
        self.assertEqual(athlete.organization_id, self.org.pk)

        profile = AthleteProfile.objects.get(athlete=athlete)
        self.assertEqual(profile.organization_id, self.org.pk)

        # No cross-org leakage
        other_org = _make_org("Other Org")
        self.assertFalse(Athlete.objects.filter(
            user=self.user, organization=other_org,
        ).exists())
