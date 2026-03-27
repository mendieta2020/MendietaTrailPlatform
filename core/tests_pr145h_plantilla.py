"""
core/tests_pr145h_plantilla.py

API tests for PR-145h: Plantilla de Entrenamiento.

Coverage:
- test_bulk_create_success            — 3 athletes, 3 assignments created
- test_bulk_create_idempotent         — second call skips, no duplicates
- test_bulk_create_athlete_not_in_org — 400 when athlete from other org
- test_compliance_week_correct_colors — grid returns correct dot colors
- test_compliance_week_single_query   — no N+1 queries (assertNumQueries)
- test_team_members_add_remove        — add + remove athlete via members endpoints
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    Membership,
    Organization,
    PlannedWorkout,
    Team,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()

WEEK_MON = datetime.date(2026, 3, 30)  # Monday


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="pass")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=is_active)


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _athlete(user, org, team=None):
    return Athlete.objects.create(user=user, organization=org, team=team)


def _library(org):
    return WorkoutLibrary.objects.create(organization=org, name="Lib")


def _workout(org, lib, name="WO"):
    return PlannedWorkout.objects.create(
        organization=org, library=lib, name=name, discipline="run", session_type="base"
    )


def _assignment(org, athlete, workout, date, status=WorkoutAssignment.Status.PLANNED,
                compliance_color="gray"):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=date,
        status=status,
        compliance_color=compliance_color,
    )


# ---------------------------------------------------------------------------
# Base setup for most tests
# ---------------------------------------------------------------------------

class PlantillaBaseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _org("PlantillaOrg")

        self.coach_user = _user("plantilla_coach")
        _membership(self.coach_user, self.org, "coach")
        _coach(self.coach_user, self.org)
        self.client.force_authenticate(user=self.coach_user)

        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

        self.team = Team.objects.create(organization=self.org, name="Alpha Team")

        self.ath1_user = _user("pa1")
        _membership(self.ath1_user, self.org, "athlete")
        self.ath1 = _athlete(self.ath1_user, self.org, team=self.team)

        self.ath2_user = _user("pa2")
        _membership(self.ath2_user, self.org, "athlete")
        self.ath2 = _athlete(self.ath2_user, self.org, team=self.team)

        self.ath3_user = _user("pa3")
        _membership(self.ath3_user, self.org, "athlete")
        self.ath3 = _athlete(self.ath3_user, self.org, team=self.team)

        self.bulk_url = f"/api/p1/orgs/{self.org.pk}/assignments/bulk-create/"
        self.compliance_url = (
            f"/api/p1/orgs/{self.org.pk}/teams/{self.team.pk}/compliance-week/"
        )
        self.members_url = f"/api/p1/orgs/{self.org.pk}/teams/{self.team.pk}/members/"

    def _bulk_payload(self, athlete_ids=None):
        return {
            "athlete_ids": athlete_ids or [self.ath1.pk, self.ath2.pk, self.ath3.pk],
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-04-07",
        }


# ---------------------------------------------------------------------------
# 1. bulk_create success
# ---------------------------------------------------------------------------

class BulkCreateSuccessTests(PlantillaBaseTests):
    def test_bulk_create_success(self):
        response = self.client.post(self.bulk_url, self._bulk_payload(), format="json")
        self.assertEqual(response.status_code, 201)
        data = response.data
        self.assertEqual(data["created"], 3)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(len(data["assignments"]), 3)
        # Verify DB records
        count = WorkoutAssignment.objects.filter(
            organization=self.org,
            planned_workout=self.workout,
            scheduled_date=datetime.date(2026, 4, 7),
        ).count()
        self.assertEqual(count, 3)


# ---------------------------------------------------------------------------
# 2. bulk_create idempotency
# ---------------------------------------------------------------------------

class BulkCreateIdempotentTests(PlantillaBaseTests):
    def test_bulk_create_idempotent(self):
        payload = self._bulk_payload()
        # First call
        r1 = self.client.post(self.bulk_url, payload, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.data["created"], 3)

        # Second call — all skip
        r2 = self.client.post(self.bulk_url, payload, format="json")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r2.data["created"], 0)
        self.assertEqual(r2.data["skipped"], 3)

        # DB should still have exactly 3 records (no duplicates)
        count = WorkoutAssignment.objects.filter(
            organization=self.org,
            planned_workout=self.workout,
            scheduled_date=datetime.date(2026, 4, 7),
        ).count()
        self.assertEqual(count, 3)


# ---------------------------------------------------------------------------
# 3. bulk_create with athlete not in org → 400
# ---------------------------------------------------------------------------

class BulkCreateCrossOrgTests(PlantillaBaseTests):
    def test_bulk_create_athlete_not_in_org(self):
        other_org = _org("OtherOrg")
        other_user = _user("other_ath")
        other_ath = _athlete(other_user, other_org)

        payload = self._bulk_payload(athlete_ids=[self.ath1.pk, other_ath.pk])
        response = self.client.post(self.bulk_url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("athlete_ids", response.data)


# ---------------------------------------------------------------------------
# 4. compliance_week correct colors
# ---------------------------------------------------------------------------

class ComplianceWeekColorsTests(PlantillaBaseTests):
    def test_compliance_week_correct_colors(self):
        # ath1: completed green on Monday
        _assignment(
            self.org, self.ath1, self.workout, WEEK_MON,
            status=WorkoutAssignment.Status.COMPLETED, compliance_color="green"
        )
        # ath2: planned on Wednesday (gray)
        _assignment(
            self.org, self.ath2, self.workout,
            WEEK_MON + datetime.timedelta(days=2),
            status=WorkoutAssignment.Status.PLANNED,
        )
        # ath3: no assignments

        response = self.client.get(self.compliance_url, {"week": "2026-03-30"})
        self.assertEqual(response.status_code, 200)

        by_id = {a["athlete_id"]: a for a in response.data["athletes"]}

        # ath1: Monday should be green
        ath1_monday = by_id[self.ath1.pk]["days"]["2026-03-30"]
        self.assertIsNotNone(ath1_monday)
        self.assertEqual(ath1_monday["color"], "green")

        # ath2: Wednesday should be gray (planned, not completed)
        ath2_wednesday = by_id[self.ath2.pk]["days"]["2026-04-01"]
        self.assertIsNotNone(ath2_wednesday)
        self.assertEqual(ath2_wednesday["color"], "gray")

        # ath3: all days null
        ath3_days = by_id[self.ath3.pk]["days"]
        for day_val in ath3_days.values():
            self.assertIsNone(day_val)

        # Response structure
        self.assertEqual(response.data["week_start"], "2026-03-30")
        self.assertEqual(response.data["week_end"], "2026-04-05")


# ---------------------------------------------------------------------------
# 5. compliance_week single query (no N+1)
# ---------------------------------------------------------------------------

class ComplianceWeekQueryCountTests(PlantillaBaseTests):
    def test_compliance_week_single_query(self):
        # Add some assignments to populate the week
        for i, ath in enumerate([self.ath1, self.ath2, self.ath3]):
            _assignment(
                self.org, ath, self.workout,
                WEEK_MON + datetime.timedelta(days=i),
                status=WorkoutAssignment.Status.COMPLETED,
                compliance_color="green",
            )

        # Force auth hits DB once; after that, compliance_week should use
        # a bounded number of queries regardless of athlete count.
        # We assert the total count stays well below N*athletes (N+1 smell).
        with self.assertNumQueries(5):
            response = self.client.get(self.compliance_url, {"week": "2026-03-30"})
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# 6. Team members add / remove
# ---------------------------------------------------------------------------

class TeamMembersTests(PlantillaBaseTests):
    def setUp(self):
        super().setUp()
        # Create a fresh athlete NOT in the team yet
        self.new_user = _user("pm_new")
        _membership(self.new_user, self.org, "athlete")
        self.new_ath = _athlete(self.new_user, self.org, team=None)

    def test_team_members_add_remove(self):
        # GET — verify initial members (ath1, ath2, ath3)
        r = self.client.get(self.members_url)
        self.assertEqual(r.status_code, 200)
        ids = {m["athlete_id"] for m in r.data}
        self.assertIn(self.ath1.pk, ids)

        # POST — add new athlete
        r = self.client.post(self.members_url, {"athlete_id": self.new_ath.pk}, format="json")
        self.assertEqual(r.status_code, 201)
        self.new_ath.refresh_from_db()
        self.assertEqual(self.new_ath.team_id, self.team.pk)

        # DELETE — remove athlete
        delete_url = f"{self.members_url}{self.ath1.pk}/"
        r = self.client.delete(delete_url)
        self.assertEqual(r.status_code, 204)
        self.ath1.refresh_from_db()
        self.assertIsNone(self.ath1.team_id)
