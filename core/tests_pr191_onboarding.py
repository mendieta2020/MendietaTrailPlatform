"""
PR-191 — Onboarding coach auto-link tests.

Verifies that Athlete.coach is set to the org's primary active coach
when an athlete completes onboarding, and that the athlete is
immediately visible in the coach's roster.
"""

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteInvitation,
    Coach,
    CoachPricingPlan,
    Membership,
    Organization,
)

User = get_user_model()

_DEFAULT_AVAILABILITY = [
    {"day_of_week": i, "is_available": i < 5, "reason": "", "preferred_time": ""}
    for i in range(7)
]


def _make_org(name="PR191 Org"):
    slug = name.lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:4]}"
    return Organization.objects.create(name=name, slug=slug)


def _make_user(email=None):
    email = email or f"u_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password="TestPass123!")


def _make_plan(org):
    return CoachPricingPlan.objects.create(
        organization=org,
        name="Basic",
        price_ars="38000.00",
        mp_plan_id=f"mp_{uuid.uuid4().hex[:6]}",
        is_active=True,
    )


def _make_invitation(org, plan, email):
    return AthleteInvitation.objects.create(
        organization=org,
        coach_plan=plan,
        email=email,
        expires_at=timezone.now() + timedelta(days=30),
    )


def _make_coach(org):
    """Create a Coach user + Membership + Coach record for the org."""
    user = _make_user()
    Membership.objects.create(user=user, organization=org, role="coach")
    return Coach.objects.create(user=user, organization=org, is_active=True)


class OnboardingCoachAutolinkTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/onboarding/complete/"
        self.org = _make_org()
        self.plan = _make_plan(self.org)
        self.athlete_user = _make_user(email="athlete_pr191@test.com")
        self.invite = _make_invitation(self.org, self.plan, self.athlete_user.email)

    def _payload(self):
        return {
            "invitation_token": str(self.invite.token),
            "first_name": "Test",
            "last_name": "Athlete",
            "birth_date": "1995-01-01",
            "weight_kg": 70.0,
            "height_cm": 170.0,
            "phone_number": "+5491100000000",
            "availability": _DEFAULT_AVAILABILITY,
        }

    def _post_onboarding(self):
        self.client.force_authenticate(self.athlete_user)
        return self.client.post(self.url, self._payload(), format="json")

    def test_athlete_coach_autolinked(self):
        """Athlete.coach is set to the org's active coach after onboarding."""
        coach = _make_coach(self.org)

        resp = self._post_onboarding()

        self.assertIn(
            resp.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Unexpected status: {resp.status_code} — {resp.data}",
        )
        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        self.assertIsNotNone(athlete.coach, "Athlete.coach must not be None when an active coach exists")
        self.assertEqual(athlete.coach_id, coach.pk)

    def test_athlete_appears_in_roster_for_coach(self):
        """After onboarding the athlete is visible via AthleteRosterViewSet for the coach."""
        coach = _make_coach(self.org)
        self._post_onboarding()

        roster_url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        self.client.force_authenticate(coach.user)
        resp = self.client.get(roster_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        # Support both paginated (results key) and plain list responses.
        items = resp.data.get("results", resp.data) if isinstance(resp.data, dict) else resp.data
        ids = [a["id"] for a in items]
        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        self.assertIn(athlete.pk, ids, "Onboarded athlete must appear in coach's roster")

    def test_no_crash_when_no_active_coach(self):
        """Org with no active coach: athlete is created without crash, coach stays None."""
        resp = self._post_onboarding()

        self.assertIn(
            resp.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Unexpected status: {resp.status_code} — {resp.data}",
        )
        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        self.assertIsNone(athlete.coach, "Athlete.coach must remain None when no active coach exists")
