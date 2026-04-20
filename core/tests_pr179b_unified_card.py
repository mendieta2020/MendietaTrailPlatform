"""
core/tests_pr179b_unified_card.py

PR-179b: Unified Card + Modal — backend enrichment tests.

Coverage (9 tests):
  1. test_weather_included_in_calendar_timeline
  2. test_coach_description_surfaces_in_response
  3. test_intensity_steps_returned_for_plan
  4. test_athlete_notes_and_rpe_in_response
  5. test_athlete_role_hides_coach_comment
  6. test_coach_role_sees_coach_comment
  7. test_coach_view_fetches_timeline (regression for PR-179a gap)
  8. test_notification_payload_includes_workout_id
  9. test_athlete_session_note_notification_sent_to_coach
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    InternalMessage,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutBlock,
    WorkoutInterval,
    WorkoutLibrary,
)

User = get_user_model()

TODAY = datetime.date.today()
TOMORROW = TODAY + datetime.timedelta(days=1)


# ── Factories ──────────────────────────────────────────────────────────────────


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _alumno(user):
    alumno, _ = Alumno.objects.get_or_create(
        usuario=user,
        defaults={"nombre": user.username, "apellido": "Test"},
    )
    return alumno


def _library(org):
    return WorkoutLibrary.objects.create(organization=org, name="TestLib")


def _workout(org, library, discipline="run", description=""):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Session A",
        discipline=discipline,
        estimated_duration_seconds=3600,
        estimated_distance_meters=10000,
        description=description,
    )


def _assignment(org, athlete, workout, date, coach_user, **kwargs):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=date,
        assigned_by=coach_user,
        day_order=1,
        status=kwargs.pop("status", "planned"),
        snapshot_version=1,
        **kwargs,
    )


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _url(org_id):
    return f"/api/p1/orgs/{org_id}/calendar-timeline/"


def _params(date=None):
    d = date or TODAY
    return {"start_date": str(d), "end_date": str(d)}


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestWeatherEnrichment:
    def test_weather_included_in_calendar_timeline(self):
        """Weather snapshot stored on assignment surfaces in timeline plans."""
        org = _org("weather-org")
        coach_u = _user("coach-w")
        athlete_u = _user("ath-w")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)
        snapshot = {"temp_c": 22, "icon": "01d", "humidity": 55, "wind_kmh": 18, "precipitation_pct": 10}
        wa.weather_snapshot = snapshot
        wa.save(update_fields=["weather_snapshot"])

        client = _authed(coach_u)
        params = {**_params(), "athlete_id": str(athlete.id)}
        resp = client.get(_url(org.id), params)
        assert resp.status_code == 200
        plans = resp.data["plans"]
        assert len(plans) == 1
        assert plans[0]["weather"] == snapshot


@pytest.mark.django_db
class TestDescriptionAndSteps:
    def test_coach_description_surfaces_in_response(self):
        """PlannedWorkout.description is returned in each plan entry."""
        org = _org("desc-org")
        coach_u = _user("coach-d")
        athlete_u = _user("ath-d")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        desc = "Calentamiento 15min, bloques Z4, enfriamiento 10min."
        wo = _workout(org, lib, description=desc)
        _assignment(org, athlete, wo, TODAY, coach_u)

        client = _authed(coach_u)
        params = {**_params(), "athlete_id": str(athlete.id)}
        resp = client.get(_url(org.id), params)
        assert resp.status_code == 200
        assert resp.data["plans"][0]["description"] == desc

    def test_intensity_steps_returned_for_plan(self):
        """WorkoutBlocks + WorkoutIntervals flatten into intensity_steps list."""
        org = _org("steps-org")
        coach_u = _user("coach-s")
        athlete_u = _user("ath-s")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)

        block = WorkoutBlock.objects.create(
            organization=org,
            planned_workout=wo,
            order_index=0,
            block_type="main",
            name="Main Set",
        )
        WorkoutInterval.objects.create(
            organization=org,
            block=block,
            order_index=0,
            repetitions=5,
            duration_seconds=300,
            target_label="Z4",
            target_value_low=4,
            target_value_high=4,
            metric_type="hr_zone",
        )
        _assignment(org, athlete, wo, TODAY, coach_u)

        client = _authed(coach_u)
        params = {**_params(), "athlete_id": str(athlete.id)}
        resp = client.get(_url(org.id), params)
        assert resp.status_code == 200
        steps = resp.data["plans"][0]["intensity_steps"]
        assert len(steps) == 1
        step = steps[0]
        assert step["block_type"] == "main"
        assert step["repetitions"] == 5
        assert step["duration_sec"] == 300
        assert step["intensity_label"] == "Z4"
        assert step["metric_type"] == "hr_zone"


@pytest.mark.django_db
class TestAthleteNotesAndRpe:
    def test_athlete_notes_and_rpe_in_response(self):
        """athlete_notes and rpe appear in both athlete and coach views."""
        org = _org("notes-org")
        coach_u = _user("coach-n")
        athlete_u = _user("ath-n")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)
        wa.athlete_notes = "Piernas pesadas hoy."
        wa.rpe = 4
        wa.save(update_fields=["athlete_notes", "rpe"])

        for role_user in (coach_u, athlete_u):
            client = _authed(role_user)
            params = _params()
            if role_user == coach_u:
                params["athlete_id"] = str(athlete.id)
            resp = client.get(_url(org.id), params)
            assert resp.status_code == 200
            plan = resp.data["plans"][0]
            assert plan["athlete_notes"] == "Piernas pesadas hoy."
            assert plan["rpe"] == 4


@pytest.mark.django_db
class TestRoleScopedFields:
    def test_athlete_role_hides_coach_comment(self):
        """coach_comment is stripped from the response for athlete role."""
        org = _org("role-org-a")
        coach_u = _user("coach-ra")
        athlete_u = _user("ath-ra")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)
        wa.coach_comment = "Privado: atleta fuerza en piernas D."
        wa.save(update_fields=["coach_comment"])

        client = _authed(athlete_u)
        resp = client.get(_url(org.id), _params())
        assert resp.status_code == 200
        plan = resp.data["plans"][0]
        assert "coach_comment" not in plan

    def test_coach_role_sees_coach_comment(self):
        """coach_comment is included when requester is a coach."""
        org = _org("role-org-c")
        coach_u = _user("coach-rc")
        athlete_u = _user("ath-rc")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)
        wa.coach_comment = "Vigilar cadencia."
        wa.save(update_fields=["coach_comment"])

        client = _authed(coach_u)
        resp = client.get(_url(org.id), {"start_date": str(TODAY), "end_date": str(TODAY), "athlete_id": str(athlete.id)})
        assert resp.status_code == 200
        plan = resp.data["plans"][0]
        assert plan.get("coach_comment") == "Vigilar cadencia."


@pytest.mark.django_db
class TestCoachViewTimeline:
    def test_coach_view_fetches_timeline(self):
        """Regression: coach can request calendar-timeline for an athlete (PR-179a gap)."""
        org = _org("coach-tl-org")
        coach_u = _user("coach-tl")
        athlete_u = _user("ath-tl")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        _assignment(org, athlete, wo, TODAY, coach_u)

        client = _authed(coach_u)
        resp = client.get(
            _url(org.id),
            {"start_date": str(TODAY), "end_date": str(TODAY), "athlete_id": str(athlete.id)},
        )
        assert resp.status_code == 200
        assert len(resp.data["plans"]) == 1
        assert resp.data["plans"][0]["id"] is not None


@pytest.mark.django_db
class TestNotificationPayload:
    def test_notification_payload_includes_workout_id(self):
        """
        When a coach posts a comment on an assignment, the resulting
        InternalMessage carries reference_id = assignment.pk (the workout link).
        """
        org = _org("notif-org")
        coach_u = _user("coach-notif")
        athlete_u = _user("ath-notif")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)

        client = _authed(coach_u)
        url = f"/api/p1/orgs/{org.id}/assignments/{wa.pk}/coach-comment/"
        resp = client.patch(url, {"coach_comment": "Excelente técnica hoy."}, format="json")
        assert resp.status_code == 200

        msg = InternalMessage.objects.filter(
            organization=org,
            recipient=athlete_u,
            alert_type="session_comment",
        ).first()
        assert msg is not None
        assert msg.reference_id == wa.pk

    def test_athlete_session_note_notification_sent_to_coach(self):
        """
        When an athlete saves athlete_notes on their own assignment,
        an InternalMessage with alert_type='athlete_session_note' is sent to the coach.
        """
        org = _org("ath-notif-org")
        coach_u = _user("coach-an")
        athlete_u = _user("ath-an")
        _membership(coach_u, org, "coach")
        _membership(athlete_u, org, "athlete")
        athlete = _athlete(athlete_u, org)
        _alumno(athlete_u)
        lib = _library(org)
        wo = _workout(org, lib)
        wa = _assignment(org, athlete, wo, TODAY, coach_u)

        # Athlete owns this assignment — partial_update with athlete_notes
        client = _authed(athlete_u)
        url = f"/api/p1/orgs/{org.id}/assignments/{wa.pk}/"
        resp = client.patch(url, {"athlete_notes": "Me sentí muy bien."}, format="json")
        assert resp.status_code == 200

        msg = InternalMessage.objects.filter(
            organization=org,
            alert_type="athlete_session_note",
        ).first()
        assert msg is not None
        assert msg.reference_id == wa.pk
        assert msg.recipient == coach_u
