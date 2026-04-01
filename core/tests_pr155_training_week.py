"""
tests_pr155_training_week.py

Tests for PR-155: TrainingWeek model and TrainingWeekViewSet.

Coverage:
- Model: UniqueConstraint, week_start Monday enforcement, cross-org tenancy guard
- ViewSet list: org-scoped, returns all athletes with their phase
- ViewSet create: upsert idempotency, coach-only write gate, invalid phase rejected
- Cross-org isolation: listing cannot leak athletes from other orgs
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Athlete, Membership, Organization, TrainingWeek

User = get_user_model()

# ── Helpers ────────────────────────────────────────────────────────────────────

MONDAY = datetime.date(2026, 4, 6)   # confirmed Monday (2026-04-06)
TUESDAY = datetime.date(2026, 4, 7)  # Tuesday — invalid week_start


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


def _tw_url(org_id):
    return f"/api/p1/orgs/{org_id}/training-weeks/"


# ── Model tests ────────────────────────────────────────────────────────────────

class TrainingWeekModelTest(TestCase):

    def setUp(self):
        self.org = _make_org("Org155Model")
        self.other_org = _make_org("OtherOrg155Model")
        self.user = _make_user("muser155")
        _make_membership(self.user, self.org, "athlete")
        self.athlete = _make_athlete(self.user, self.org)

    def test_create_valid(self):
        tw = TrainingWeek.objects.create(
            organization=self.org,
            athlete=self.athlete,
            week_start=MONDAY,
            phase="carga",
        )
        self.assertIsNotNone(tw.pk)
        self.assertEqual(tw.phase, "carga")

    def test_week_start_must_be_monday(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            TrainingWeek.objects.create(
                organization=self.org,
                athlete=self.athlete,
                week_start=TUESDAY,
                phase="carga",
            )

    def test_unique_constraint_athlete_week(self):
        from django.db import IntegrityError
        TrainingWeek.objects.create(
            organization=self.org, athlete=self.athlete,
            week_start=MONDAY, phase="carga",
        )
        # Bypass model's save() to hit the DB constraint directly
        with self.assertRaises(Exception):
            TrainingWeek(
                organization=self.org, athlete=self.athlete,
                week_start=MONDAY, phase="descarga",
            ).save()

    def test_cross_org_validation_rejected(self):
        """organization must match athlete.organization — fails with ValidationError."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            TrainingWeek.objects.create(
                organization=self.other_org,
                athlete=self.athlete,  # athlete belongs to self.org
                week_start=MONDAY,
                phase="carga",
            )

    def test_str(self):
        tw = TrainingWeek.objects.create(
            organization=self.org, athlete=self.athlete,
            week_start=MONDAY, phase="carrera",
        )
        self.assertIn("carrera", str(tw))


# ── API tests ──────────────────────────────────────────────────────────────────

class TrainingWeekAPITest(TestCase):

    def setUp(self):
        self.org = _make_org("Org155API")
        self.other_org = _make_org("OtherOrg155API")

        # Coach
        self.coach_user = _make_user("coach155")
        _make_membership(self.coach_user, self.org, "coach")

        # Athlete 1
        self.athlete_user = _make_user("ath155a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Athlete 2
        self.athlete2_user = _make_user("ath155b")
        _make_membership(self.athlete2_user, self.org, "athlete")
        self.athlete2 = _make_athlete(self.athlete2_user, self.org)

        # Other org athlete
        self.other_user = _make_user("other155")
        _make_membership(self.other_user, self.other_org, "athlete")
        self.other_athlete = _make_athlete(self.other_user, self.other_org)

        # Other org coach (must not see our org)
        self.other_coach_user = _make_user("othercoach155")
        _make_membership(self.other_coach_user, self.other_org, "coach")

    def _coach_client(self):
        c = APIClient()
        c.force_authenticate(user=self.coach_user)
        return c

    def _athlete_client(self):
        c = APIClient()
        c.force_authenticate(user=self.athlete_user)
        return c

    # ── List ────────────────────────────────────────────────────────────────

    def test_list_returns_both_athletes(self):
        c = self._coach_client()
        resp = c.get(_tw_url(self.org.id) + "?week_start=2026-04-07")
        self.assertEqual(resp.status_code, 200)
        athlete_ids = [r["athlete_id"] for r in resp.data]
        self.assertIn(self.athlete.id, athlete_ids)
        self.assertIn(self.athlete2.id, athlete_ids)

    def test_list_includes_existing_phase(self):
        TrainingWeek.objects.create(
            organization=self.org, athlete=self.athlete,
            week_start=MONDAY, phase="descarga",
        )
        c = self._coach_client()
        resp = c.get(_tw_url(self.org.id) + "?week_start=2026-04-07")
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.data if r["athlete_id"] == self.athlete.id)
        self.assertEqual(row["phase"], "descarga")

    def test_list_athlete_sees_only_self(self):
        c = self._athlete_client()
        resp = c.get(_tw_url(self.org.id) + "?week_start=2026-04-07")
        self.assertEqual(resp.status_code, 200)
        athlete_ids = [r["athlete_id"] for r in resp.data]
        self.assertIn(self.athlete.id, athlete_ids)
        self.assertNotIn(self.athlete2.id, athlete_ids)

    def test_list_excludes_other_org_athletes(self):
        c = self._coach_client()
        resp = c.get(_tw_url(self.org.id) + "?week_start=2026-04-07")
        self.assertEqual(resp.status_code, 200)
        athlete_ids = [r["athlete_id"] for r in resp.data]
        self.assertNotIn(self.other_athlete.id, athlete_ids)

    def test_list_snaps_non_monday_to_monday(self):
        """Passing a Tuesday still returns the Monday row."""
        TrainingWeek.objects.create(
            organization=self.org, athlete=self.athlete,
            week_start=MONDAY, phase="carga",
        )
        c = self._coach_client()
        resp = c.get(_tw_url(self.org.id) + "?week_start=2026-04-07")  # Tuesday → snaps to 2026-04-06
        self.assertEqual(resp.status_code, 200)
        row = next((r for r in resp.data if r["athlete_id"] == self.athlete.id), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["phase"], "carga")

    # ── Create / Upsert ─────────────────────────────────────────────────────

    def test_create_returns_201(self):
        c = self._coach_client()
        resp = c.post(_tw_url(self.org.id), {
            "athlete_id": self.athlete.id,
            "week_start": "2026-04-06",
            "phase": "carga",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(TrainingWeek.objects.filter(
            athlete=self.athlete, week_start=MONDAY, phase="carga"
        ).exists())

    def test_upsert_is_idempotent(self):
        """Second POST for same athlete+week updates phase and returns 200."""
        c = self._coach_client()
        url = _tw_url(self.org.id)
        c.post(url, {"athlete_id": self.athlete.id, "week_start": "2026-04-06", "phase": "carga"}, format="json")
        resp = c.post(url, {"athlete_id": self.athlete.id, "week_start": "2026-04-06", "phase": "descarga"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TrainingWeek.objects.filter(athlete=self.athlete, week_start=MONDAY).count(), 1)
        self.assertEqual(TrainingWeek.objects.get(athlete=self.athlete, week_start=MONDAY).phase, "descarga")

    def test_athlete_cannot_post(self):
        c = self._athlete_client()
        resp = c.post(_tw_url(self.org.id), {
            "athlete_id": self.athlete.id,
            "week_start": "2026-04-06",
            "phase": "carga",
        }, format="json")
        self.assertIn(resp.status_code, [403, 401])

    def test_invalid_phase_returns_400(self):
        c = self._coach_client()
        resp = c.post(_tw_url(self.org.id), {
            "athlete_id": self.athlete.id,
            "week_start": "2026-04-06",
            "phase": "invalid_phase",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_missing_required_fields_returns_400(self):
        c = self._coach_client()
        resp = c.post(_tw_url(self.org.id), {"phase": "carga"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_cross_org_athlete_rejected(self):
        """Coach cannot assign phase to an athlete from another org."""
        c = self._coach_client()
        resp = c.post(_tw_url(self.org.id), {
            "athlete_id": self.other_athlete.id,
            "week_start": "2026-04-06",
            "phase": "carga",
        }, format="json")
        # 404 because get_object_or_404 filters by organization
        self.assertEqual(resp.status_code, 404)
