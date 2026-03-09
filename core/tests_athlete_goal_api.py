"""
core/tests_athlete_goal_api.py

API tests for PR-115: RaceEvent + AthleteGoal CRUD endpoints.

Coverage:
- Unauthenticated rejected (401)
- No membership rejected (403)
- Inactive membership rejected (403)
- Coach CRUD for RaceEvent (201 / 200 / 204)
- Athlete read-only for RaceEvent (200 list/retrieve; 403 on write)
- Coach cannot access another org's events (empty queryset / 404 on detail)
- Coach CRUD for AthleteGoal
- Athlete reads own goals only; cannot see other athletes' goals
- Athlete cannot create/update/delete goals (403)
- Cross-org athlete_id rejected by serializer (400)
- Cross-org target_event_id rejected by serializer (400)
- Valid target_event link accepted (201)
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Athlete, AthleteGoal, Coach, Membership, Organization, RaceEvent

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


def _make_race_event(org, name="Race A", event_date=None):
    if event_date is None:
        event_date = datetime.date(2026, 6, 1)
    return RaceEvent.objects.create(
        organization=org,
        name=name,
        discipline="trail",
        event_date=event_date,
    )


def _make_goal(org, athlete, title="Goal A", priority="A"):
    return AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        title=title,
        priority=priority,
        goal_type="finish",
        status="planned",
    )


def _race_event_list_url(org_id):
    return f"/api/p1/orgs/{org_id}/race-events/"


def _race_event_detail_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/race-events/{pk}/"


def _goal_list_url(org_id):
    return f"/api/p1/orgs/{org_id}/goals/"


def _goal_detail_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/goals/{pk}/"


# ==============================================================================
# RaceEvent API Tests
# ==============================================================================

class RaceEventAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        # Org A — primary
        self.org = _make_org("OrgA")

        # Coach user
        self.coach_user = _make_user("coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete user
        self.athlete_user = _make_user("athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        _make_athlete(self.athlete_user, self.org)

        # Org B — for cross-org isolation tests
        self.org_b = _make_org("OrgB")
        self.coach_b_user = _make_user("coach_b")
        _make_membership(self.coach_b_user, self.org_b, "coach")

        # Existing race event in org A
        self.event = _make_race_event(self.org, name="Trail Alpha")

        self.list_url = _race_event_list_url(self.org.id)
        self.detail_url = _race_event_detail_url(self.org.id, self.event.pk)

    def _post_payload(self, name="New Race"):
        return {
            "name": name,
            "discipline": "trail",
            "event_date": "2026-09-15",
        }

    # --- Auth / membership gate ---

    def test_unauthenticated_list_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_create_rejected(self):
        response = self.client.post(self.list_url, self._post_payload(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_no_membership_rejected(self):
        stranger = _make_user("stranger")
        self.client.force_authenticate(user=stranger)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_rejected(self):
        inactive_user = _make_user("inactive_u")
        _make_membership(inactive_user, self.org, "coach", is_active=False)
        self.client.force_authenticate(user=inactive_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    # --- Coach CRUD ---

    def test_coach_can_list_race_events(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.event.pk, ids)

    def test_coach_can_retrieve_race_event(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Trail Alpha")

    def test_coach_can_create_race_event(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.post(self.list_url, self._post_payload("New Race"), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(RaceEvent.objects.filter(name="New Race", organization=self.org).exists())

    def test_created_race_event_belongs_to_request_org(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(self.list_url, self._post_payload("Org Bound"), format="json")
        event = RaceEvent.objects.get(name="Org Bound")
        self.assertEqual(event.organization_id, self.org.id)

    def test_coach_can_update_race_event(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "name": "Trail Alpha Updated",
            "discipline": "trail",
            "event_date": "2026-06-01",
        }
        response = self.client.put(self.detail_url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, "Trail Alpha Updated")

    def test_coach_can_partial_update_race_event(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(self.detail_url, {"location": "Zermatt"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.location, "Zermatt")

    def test_coach_can_delete_race_event(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(RaceEvent.objects.filter(pk=self.event.pk).exists())

    # --- Athlete read-only ---

    def test_athlete_can_list_race_events(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.event.pk, ids)

    def test_athlete_can_retrieve_race_event(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)

    def test_athlete_cannot_create_race_event(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.post(self.list_url, self._post_payload("Athlete Race"), format="json")
        self.assertEqual(response.status_code, 403)

    def test_athlete_cannot_update_race_event(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(self.detail_url, {"location": "Hacked"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_athlete_cannot_delete_race_event(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 403)

    # --- Org isolation ---

    def test_org_list_excludes_other_org_events(self):
        """Coach A's list must not include Org B's events."""
        _make_race_event(self.org_b, name="Org B Race")
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        names = [r["name"] for r in response.data["results"]]
        self.assertNotIn("Org B Race", names)

    def test_cross_org_coach_cannot_list_via_wrong_org_url(self):
        """Coach B has no membership in Org A → 403."""
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_cross_org_coach_cannot_retrieve_via_wrong_org_url(self):
        """Coach B cannot fetch an Org A event detail via Org A URL."""
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)


# ==============================================================================
# AthleteGoal API Tests
# ==============================================================================

class AthleteGoalAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        # Org A
        self.org = _make_org("GoalOrgA")

        # Coach
        self.coach_user = _make_user("goal_coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete 1
        self.athlete_user = _make_user("goal_athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Athlete 2 (same org)
        self.athlete2_user = _make_user("goal_athlete_b")
        _make_membership(self.athlete2_user, self.org, "athlete")
        self.athlete2 = _make_athlete(self.athlete2_user, self.org)

        # Org B — cross-org fixtures
        self.org_b = _make_org("GoalOrgB")
        self.athlete_b_user = _make_user("athlete_b_cross")
        _make_membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _make_athlete(self.athlete_b_user, self.org_b)

        # Race event in org A
        self.event = _make_race_event(self.org, name="Goal Race")

        # Race event in org B (for cross-org rejection)
        self.event_b = _make_race_event(self.org_b, name="Org B Race")

        # Existing goal for athlete 1
        self.goal = _make_goal(self.org, self.athlete, title="My Goal", priority="A")

        # Existing goal for athlete 2
        self.goal2 = _make_goal(self.org, self.athlete2, title="Other Athlete Goal", priority="B")

        self.list_url = _goal_list_url(self.org.id)
        self.detail_url = _goal_detail_url(self.org.id, self.goal.pk)
        self.detail2_url = _goal_detail_url(self.org.id, self.goal2.pk)

    def _create_payload(self, athlete_id=None, priority="B", target_event_id=None):
        payload = {
            "title": "New Goal",
            "athlete_id": athlete_id or self.athlete.pk,
            "priority": priority,
            "goal_type": "finish",
            "status": "planned",
        }
        if target_event_id is not None:
            payload["target_event_id"] = target_event_id
        return payload

    # --- Auth / membership gate ---

    def test_unauthenticated_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_no_membership_rejected(self):
        stranger = _make_user("goal_stranger")
        self.client.force_authenticate(user=stranger)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_rejected(self):
        inactive = _make_user("goal_inactive")
        _make_membership(inactive, self.org, "coach", is_active=False)
        self.client.force_authenticate(user=inactive)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    # --- Coach CRUD ---

    def test_coach_can_list_all_org_goals(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.goal.pk, ids)
        self.assertIn(self.goal2.pk, ids)

    def test_coach_can_retrieve_any_goal(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail2_url)
        self.assertEqual(response.status_code, 200)

    def test_coach_can_create_goal(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.post(
            self.list_url, self._create_payload(priority="C"), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            AthleteGoal.objects.filter(title="New Goal", organization=self.org).exists()
        )

    def test_created_goal_belongs_to_request_org(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(self.list_url, self._create_payload(priority="C"), format="json")
        goal = AthleteGoal.objects.get(title="New Goal")
        self.assertEqual(goal.organization_id, self.org.id)

    def test_coach_can_update_goal(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "title": "Updated Title",
            "athlete_id": self.athlete.pk,
            "priority": "A",
            "goal_type": "finish",
            "status": "active",
        }
        response = self.client.put(self.detail_url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.title, "Updated Title")

    def test_coach_can_partial_update_goal(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"coach_notes": "Focus on hills"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.coach_notes, "Focus on hills")

    def test_coach_can_delete_goal(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AthleteGoal.objects.filter(pk=self.goal.pk).exists())

    # --- Athlete read-only ---

    def test_athlete_can_list_own_goals_only(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.goal.pk, ids)
        self.assertNotIn(self.goal2.pk, ids)

    def test_athlete_can_retrieve_own_goal(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)

    def test_athlete_cannot_retrieve_other_athlete_goal(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail2_url)
        self.assertEqual(response.status_code, 404)

    def test_athlete_cannot_create_goal(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.post(
            self.list_url, self._create_payload(priority="C"), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_athlete_cannot_update_goal(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"coach_notes": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_athlete_cannot_delete_goal(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 403)

    # --- Cross-org FK validation ---

    def test_cross_org_athlete_id_rejected(self):
        """Passing an athlete from Org B to Org A's goal endpoint is rejected."""
        self.client.force_authenticate(user=self.coach_user)
        payload = self._create_payload(athlete_id=self.athlete_b.pk, priority="C")
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cross_org_target_event_id_rejected(self):
        """Passing a RaceEvent from Org B to Org A's goal endpoint is rejected."""
        self.client.force_authenticate(user=self.coach_user)
        payload = self._create_payload(priority="C", target_event_id=self.event_b.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_valid_target_event_link_accepted(self):
        """Linking a goal to a RaceEvent in the same org is accepted."""
        self.client.force_authenticate(user=self.coach_user)
        payload = self._create_payload(priority="C", target_event_id=self.event.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        goal = AthleteGoal.objects.get(title="New Goal")
        self.assertEqual(goal.target_event_id, self.event.pk)

    def test_null_target_event_accepted(self):
        """Creating a goal without a target_event (personal goal) is valid."""
        self.client.force_authenticate(user=self.coach_user)
        payload = self._create_payload(priority="C")
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        goal = AthleteGoal.objects.get(title="New Goal")
        self.assertIsNone(goal.target_event_id)
