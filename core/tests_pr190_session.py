"""
core/tests_pr190_session.py — PR-190

Tests for:
  - Fix 1: RaceEvent delete cancels linked AthleteGoals
  - Fix 2: GET /messages/?reference_id=<n> returns only session thread (tenancy-safe)
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteGoal,
    InternalMessage,
    Membership,
    Organization,
    RaceEvent,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniq(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _org(slug=None) -> Organization:
    slug = slug or _uniq("org-")
    return Organization.objects.create(name=slug.title(), slug=slug)


def _user(username=None) -> User:
    username = username or _uniq("user-")
    return User.objects.create_user(username=username, password="pass1234", email=f"{username}@test.com")


def _membership(user, org, role="coach") -> Membership:
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _athlete_record(user, org) -> Athlete:
    return Athlete.objects.create(user=user, organization=org, is_active=True)


def _race_event(org, name=None) -> RaceEvent:
    import datetime
    name = name or f"Race {_uniq()}"
    return RaceEvent.objects.create(
        organization=org,
        name=name,
        discipline="trail",
        event_date=datetime.date(2027, 6, 1),
    )


def _athlete_goal(org, athlete, race_event=None, status="planned", priority="B") -> AthleteGoal:
    import datetime
    return AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        target_event=race_event,
        target_date=datetime.date(2027, 6, 1),
        title=f"Goal {_uniq()}",
        priority=priority,
        status=status,
    )


def _internal_msg(org, sender, recipient, reference_id=None, content="msg") -> InternalMessage:
    import datetime
    return InternalMessage.objects.create(
        organization=org,
        sender=sender,
        recipient=recipient,
        content=content,
        reference_id=reference_id,
    )


# ---------------------------------------------------------------------------
# Fix 1: RaceEvent delete → cancel linked AthleteGoals
# ---------------------------------------------------------------------------

class TestRaceEventDeleteCancelsGoals(TestCase):
    def setUp(self):
        self.org = _org()
        self.coach = _user("coach")
        _membership(self.coach, self.org, role="coach")
        self.athlete_user = _user("athlete")
        _membership(self.athlete_user, self.org, role="athlete")
        self.athlete = _athlete_record(self.athlete_user, self.org)
        self.event = _race_event(self.org)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_delete_cancels_planned_and_active_goals(self):
        goal_planned = _athlete_goal(self.org, self.athlete, self.event, status="planned", priority="A")
        goal_active = _athlete_goal(self.org, self.athlete, self.event, status="active", priority="B")
        url = f"/api/p1/orgs/{self.org.pk}/race-events/{self.event.pk}/"
        resp = self._client(self.coach).delete(url)
        self.assertEqual(resp.status_code, 204)
        goal_planned.refresh_from_db()
        goal_active.refresh_from_db()
        self.assertEqual(goal_planned.status, "cancelled")
        self.assertEqual(goal_active.status, "cancelled")
        self.assertFalse(RaceEvent.objects.filter(pk=self.event.pk).exists())

    def test_delete_does_not_cancel_completed_goals(self):
        goal_done = _athlete_goal(self.org, self.athlete, self.event, status="completed")
        url = f"/api/p1/orgs/{self.org.pk}/race-events/{self.event.pk}/"
        self._client(self.coach).delete(url)
        goal_done.refresh_from_db()
        self.assertEqual(goal_done.status, "completed")


# ---------------------------------------------------------------------------
# Fix 2: GET /messages/?reference_id=<n> returns session thread (tenancy-safe)
# ---------------------------------------------------------------------------

class TestMessagesFilterByReferenceId(TestCase):
    def setUp(self):
        self.org = _org()
        self.coach = _user("coach2")
        _membership(self.coach, self.org, role="coach")
        self.athlete_user = _user("ath2")
        _membership(self.athlete_user, self.org, role="athlete")

        self.other_org = _org()
        self.other_coach = _user("other_coach")
        _membership(self.other_coach, self.other_org, role="coach")
        self.other_athlete = _user("other_ath")
        _membership(self.other_athlete, self.other_org, role="athlete")

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_filter_returns_only_matching_reference_id(self):
        _internal_msg(self.org, self.athlete_user, self.coach, reference_id=42, content="msg-42a")
        _internal_msg(self.org, self.coach, self.athlete_user, reference_id=42, content="msg-42b")
        _internal_msg(self.org, self.athlete_user, self.coach, reference_id=99, content="msg-99")

        url = f"/api/p1/orgs/{self.org.pk}/messages/?reference_id=42"
        resp = self._client(self.coach).get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        for m in data:
            self.assertEqual(m["reference_id"], 42)

    def test_filter_excludes_other_org_messages(self):
        _internal_msg(self.org, self.athlete_user, self.coach, reference_id=42, content="mine")
        _internal_msg(self.other_org, self.other_athlete, self.other_coach, reference_id=42, content="other")

        url = f"/api/p1/orgs/{self.org.pk}/messages/?reference_id=42"
        resp = self._client(self.coach).get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["content"], "mine")

    def test_filter_includes_is_coach_message_flag(self):
        _internal_msg(self.org, self.coach, self.athlete_user, reference_id=55, content="from coach")

        url = f"/api/p1/orgs/{self.org.pk}/messages/?reference_id=55"
        resp = self._client(self.athlete_user).get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["is_coach_message"])

    def test_list_without_reference_id_returns_normal_format(self):
        url = f"/api/p1/orgs/{self.org.pk}/messages/"
        resp = self._client(self.coach).get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertIn("unread_count", data)
