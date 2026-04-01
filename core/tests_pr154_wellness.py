"""
core/tests_pr154_wellness.py

Tests for PR-154: WellnessCheckIn model + ViewSet.

Covers:
- Model creation + validation
- UniqueConstraint on (athlete, date)
- Organization cross-tenant isolation (model clean)
- ViewSet: POST creates, GET lists, idempotent upsert on same day
- Dismiss endpoint sets wellness_checkin_dismissed=True
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Athlete, AthleteProfile, Membership, Organization, WellnessCheckIn

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _wellness_url(org_id, athlete_id):
    return f"/api/p1/orgs/{org_id}/athletes/{athlete_id}/wellness/"


def _dismiss_url(org_id, athlete_id):
    return f"/api/p1/orgs/{org_id}/athletes/{athlete_id}/wellness/dismiss/"


VALID_PAYLOAD = {
    "sleep_quality": 4,
    "mood": 3,
    "energy": 4,
    "muscle_soreness": 3,
    "stress": 4,
}

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class WellnessCheckInModelTest(TestCase):

    def setUp(self):
        self.org = _make_org("ModelOrg154")
        self.other_org = _make_org("OtherOrg154")
        self.user = _make_user("muser154")
        _make_membership(self.user, self.org, "athlete")
        self.athlete = _make_athlete(self.user, self.org)

    def test_create_basic(self):
        w = WellnessCheckIn.objects.create(
            athlete=self.athlete, organization=self.org,
            date=datetime.date.today(), **VALID_PAYLOAD,
        )
        self.assertIsNotNone(w.pk)
        self.assertEqual(w.organization_id, self.org.id)

    def test_unique_per_athlete_date(self):
        from django.db import IntegrityError
        today = datetime.date.today()
        WellnessCheckIn.objects.create(
            athlete=self.athlete, organization=self.org,
            date=today, **VALID_PAYLOAD,
        )
        with self.assertRaises(Exception):
            WellnessCheckIn.objects.create(
                athlete=self.athlete, organization=self.org,
                date=today, **{k: 5 for k in VALID_PAYLOAD},
            )

    def test_cross_org_validation_raises(self):
        from django.core.exceptions import ValidationError
        w = WellnessCheckIn(
            athlete=self.athlete,
            organization=self.other_org,
            date=datetime.date.today(),
            **VALID_PAYLOAD,
        )
        with self.assertRaises(ValidationError):
            w.full_clean()

    def test_score_out_of_range_raises(self):
        from django.core.exceptions import ValidationError
        w = WellnessCheckIn(
            athlete=self.athlete, organization=self.org,
            date=datetime.date.today(),
            sleep_quality=6, mood=3, energy=4, muscle_soreness=3, stress=4,
        )
        with self.assertRaises(ValidationError):
            w.full_clean()


# ---------------------------------------------------------------------------
# ViewSet tests
# ---------------------------------------------------------------------------

class WellnessCheckInViewSetTest(TestCase):

    def setUp(self):
        self.org = _make_org("VSOrg154")
        self.coach_user = _make_user("coach_vs154")
        _make_membership(self.coach_user, self.org, "coach")

        self.athlete_user = _make_user("athlete_vs154")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        self.coach_client = APIClient()
        self.coach_client.force_authenticate(self.coach_user)

        self.athlete_client = APIClient()
        self.athlete_client.force_authenticate(self.athlete_user)

    def test_athlete_can_post_own_checkin(self):
        url = _wellness_url(self.org.id, self.athlete.id)
        res = self.athlete_client.post(url, VALID_PAYLOAD, format="json")
        self.assertIn(res.status_code, (200, 201))
        self.assertEqual(
            WellnessCheckIn.objects.filter(athlete=self.athlete, organization=self.org).count(),
            1,
        )

    def test_post_is_idempotent_same_day(self):
        url = _wellness_url(self.org.id, self.athlete.id)
        self.athlete_client.post(url, VALID_PAYLOAD, format="json")
        res = self.athlete_client.post(
            url, {k: 5 for k in VALID_PAYLOAD}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            WellnessCheckIn.objects.filter(
                athlete=self.athlete,
                organization=self.org,
                date=datetime.date.today(),
            ).count(),
            1,
        )

    def test_coach_can_get_athlete_checkins(self):
        WellnessCheckIn.objects.create(
            athlete=self.athlete, organization=self.org,
            date=datetime.date.today(), **VALID_PAYLOAD,
        )
        url = _wellness_url(self.org.id, self.athlete.id)
        res = self.coach_client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertGreaterEqual(len(items), 1)

    def test_no_cross_org_access(self):
        other_org = _make_org("CrossOrg154")
        other_user = _make_user("other_a154")
        _make_membership(other_user, other_org, "athlete")
        other_athlete = _make_athlete(other_user, other_org)

        # self.athlete_client (org) tries to access other_org's athlete
        url = _wellness_url(other_org.id, other_athlete.id)
        res = self.athlete_client.get(url)
        self.assertIn(res.status_code, (403, 404))

    def test_dismiss_sets_flag(self):
        AthleteProfile.objects.create(athlete=self.athlete, organization=self.org)
        url = _dismiss_url(self.org.id, self.athlete.id)
        res = self.athlete_client.post(url, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["dismissed"])
        profile = AthleteProfile.objects.get(athlete=self.athlete)
        self.assertTrue(profile.wellness_checkin_dismissed)

    def test_unauthenticated_is_rejected(self):
        anon = APIClient()
        url = _wellness_url(self.org.id, self.athlete.id)
        res = anon.get(url)
        self.assertIn(res.status_code, (401, 403))
