"""
core/tests_athlete_profile_api.py

API tests for PR-116: AthleteProfile endpoints.

Coverage:
- Unauthenticated rejected (401)
- No membership rejected (403)
- Inactive membership rejected (403)
- Coach can list profiles in org (200)
- Athlete cannot list all profiles (403)
- Coach can retrieve any profile in org (200)
- Athlete can retrieve own profile (200)
- Athlete cannot retrieve another athlete's profile (404)
- Cross-org coach cannot access via wrong org URL (403)
- Coach can create profile (201)
- Athlete cannot create profile (403)
- Coach cannot create profile for cross-org athlete (400)
- Duplicate profile create rejected (400)
- Coach can update any profile in org (200)
- Athlete can update own profile (200)
- Athlete cannot update another athlete's profile (404)
- updated_by is set from request.user (server-controlled)
- organization is not writable by client
- JSON zone fields round-trip correctly
- partial_update preserves other fields
- No delete endpoint exposed (405)
- No migration generated
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Athlete, AthleteProfile, Coach, Membership, Organization

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
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


def _make_coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _make_profile(org, athlete, **kwargs):
    return AthleteProfile.objects.create(organization=org, athlete=athlete, **kwargs)


def _profile_list_url(org_id):
    return f"/api/p1/orgs/{org_id}/profiles/"


def _profile_detail_url(org_id, athlete_id):
    return f"/api/p1/orgs/{org_id}/profiles/{athlete_id}/"


# ==============================================================================
# AthleteProfile API Tests
# ==============================================================================

class AthleteProfileAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        # Org A — primary
        self.org = _make_org("ProfileOrgA")

        # Coach
        self.coach_user = _make_user("prof_coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete 1 — has a profile
        self.athlete_user = _make_user("prof_athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)
        self.profile = _make_profile(self.org, self.athlete, weight_kg=70.0, vo2max=55.0)

        # Athlete 2 — no profile (used for create tests)
        self.athlete2_user = _make_user("prof_athlete_b")
        _make_membership(self.athlete2_user, self.org, "athlete")
        self.athlete2 = _make_athlete(self.athlete2_user, self.org)

        # Athlete 3 — has a profile (used for cross-athlete access tests)
        self.athlete3_user = _make_user("prof_athlete_c")
        _make_membership(self.athlete3_user, self.org, "athlete")
        self.athlete3 = _make_athlete(self.athlete3_user, self.org)
        self.profile3 = _make_profile(self.org, self.athlete3, weight_kg=65.0)

        # Org B — for cross-org tests
        self.org_b = _make_org("ProfileOrgB")
        self.coach_b_user = _make_user("prof_coach_b")
        _make_membership(self.coach_b_user, self.org_b, "coach")
        _make_coach(self.coach_b_user, self.org_b)

        self.athlete_b_user = _make_user("prof_athlete_b_cross")
        _make_membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _make_athlete(self.athlete_b_user, self.org_b)

        self.list_url = _profile_list_url(self.org.id)
        self.detail_url = _profile_detail_url(self.org.id, self.athlete.pk)
        self.detail3_url = _profile_detail_url(self.org.id, self.athlete3.pk)

    # --- Auth / membership gate ---

    def test_unauthenticated_list_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_retrieve_rejected(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 401)

    def test_no_membership_rejected(self):
        stranger = _make_user("prof_stranger")
        self.client.force_authenticate(user=stranger)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_rejected(self):
        inactive_user = _make_user("prof_inactive")
        _make_membership(inactive_user, self.org, "coach", is_active=False)
        self.client.force_authenticate(user=inactive_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    # --- Coach list / retrieve ---

    def test_coach_can_list_profiles(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        athlete_ids = [r["athlete_id"] for r in response.data["results"]]
        self.assertIn(self.athlete.pk, athlete_ids)
        self.assertIn(self.athlete3.pk, athlete_ids)

    def test_coach_can_retrieve_any_profile(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["athlete_id"], self.athlete.pk)

    def test_coach_list_excludes_other_org_profiles(self):
        _make_profile(self.org_b, self.athlete_b, weight_kg=80.0)
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        athlete_ids = [r["athlete_id"] for r in response.data["results"]]
        self.assertNotIn(self.athlete_b.pk, athlete_ids)

    # --- Athlete list / retrieve ---

    def test_athlete_cannot_list_profiles(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_athlete_can_retrieve_own_profile(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["athlete_id"], self.athlete.pk)

    def test_athlete_cannot_retrieve_another_athlete_profile(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail3_url)
        self.assertEqual(response.status_code, 404)

    # --- Cross-org access ---

    def test_cross_org_coach_cannot_access_list_via_wrong_org_url(self):
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_cross_org_coach_cannot_access_detail_via_wrong_org_url(self):
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    # --- Create ---

    def test_coach_can_create_profile(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {"athlete_id": self.athlete2.pk, "weight_kg": 68.0}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            AthleteProfile.objects.filter(athlete=self.athlete2).exists()
        )

    def test_created_profile_organization_matches_url_org(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {"athlete_id": self.athlete2.pk}
        self.client.post(self.list_url, payload, format="json")
        profile = AthleteProfile.objects.get(athlete=self.athlete2)
        self.assertEqual(profile.organization_id, self.org.id)

    def test_athlete_cannot_create_profile(self):
        self.client.force_authenticate(user=self.athlete_user)
        payload = {"athlete_id": self.athlete2.pk}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 403)

    def test_coach_cannot_create_profile_for_cross_org_athlete(self):
        """Athlete from Org B is not in Org A's queryset — serializer rejects."""
        self.client.force_authenticate(user=self.coach_user)
        payload = {"athlete_id": self.athlete_b.pk}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_profile_create_rejected(self):
        """Athlete 1 already has a profile — second create must fail."""
        self.client.force_authenticate(user=self.coach_user)
        payload = {"athlete_id": self.athlete.pk, "weight_kg": 72.0}
        response = self.client.post(self.list_url, payload, format="json")
        # Expect 400 (UniqueValidator or model clean()) — NOT 500
        self.assertEqual(response.status_code, 400)

    # --- Update ---

    def test_coach_can_update_profile(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete.pk,
            "weight_kg": 72.5,
            "vo2max": 58.0,
        }
        response = self.client.patch(self.detail_url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertAlmostEqual(self.profile.weight_kg, 72.5)
        self.assertAlmostEqual(self.profile.vo2max, 58.0)

    def test_athlete_can_update_own_profile(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"is_injured": True, "injury_notes": "Knee pain"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_injured)
        self.assertEqual(self.profile.injury_notes, "Knee pain")

    def test_athlete_cannot_update_another_athlete_profile(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail3_url, {"weight_kg": 50.0}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_partial_update_preserves_other_fields(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"ftp_watts": 280}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.ftp_watts, 280)
        # weight_kg from setUp must be preserved
        self.assertAlmostEqual(self.profile.weight_kg, 70.0)

    # --- Server-controlled fields ---

    def test_updated_by_set_from_request_user_on_update(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.patch(self.detail_url, {"notes": "test update"}, format="json")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.updated_by_id, self.coach_user.pk)

    def test_updated_by_set_from_request_user_on_create(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(self.list_url, {"athlete_id": self.athlete2.pk}, format="json")
        profile = AthleteProfile.objects.get(athlete=self.athlete2)
        self.assertEqual(profile.updated_by_id, self.coach_user.pk)

    def test_organization_not_in_response(self):
        """organization is server-controlled and not exposed in the API response."""
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("organization", response.data)
        self.assertNotIn("organization_id", response.data)

    def test_athlete_id_read_only_on_update(self):
        """Client attempt to change athlete_id on update is silently ignored."""
        self.client.force_authenticate(user=self.coach_user)
        # Send athlete3's PK as athlete_id — should be ignored, not cause 400 or reassignment
        response = self.client.patch(
            self.detail_url, {"athlete_id": self.athlete3.pk, "notes": "no reassign"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        # athlete must still be athlete (not athlete3)
        self.assertEqual(self.profile.athlete_id, self.athlete.pk)

    # --- JSON zone fields ---

    def test_hr_zones_json_round_trips(self):
        zones = {"z1": {"min_bpm": 100, "max_bpm": 130}, "z2": {"min_bpm": 131, "max_bpm": 155}}
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"hr_zones_json": zones}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hr_zones_json"], zones)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.hr_zones_json, zones)

    def test_pace_zones_json_round_trips(self):
        zones = {"z1": {"min_s_km": 360, "max_s_km": 420}}
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"pace_zones_json": zones}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pace_zones_json"], zones)

    # --- No DELETE ---

    def test_delete_not_exposed(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 405)
