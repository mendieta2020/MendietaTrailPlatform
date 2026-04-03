"""
core/tests_pr157_periodization.py

PR-157: Auto-periodization service + endpoints.

Coverage:
  1.  suggest_cycle_pattern — distance thresholds (10/21/42/100 km)
  2.  auto_periodize_athlete — race week gets phase="carrera"
  3.  auto_periodize_athlete — taper week (before race) gets phase="descarga"
  4.  auto_periodize_athlete — post-race week gets phase="descanso"
  5.  auto_periodize_athlete — cycle 3:1 fills correctly
  6.  auto_periodize_athlete — cycle 2:1 fills correctly
  7.  auto_periodize_athlete — does NOT overwrite phase="lesion"
  8.  auto_periodize_athlete — handles multiple goals (fills between them)
  9.  recent_workouts_detects_consecutive_repetition
  10. auto_periodize_group_endpoint — processes athletes with goals, skips others
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteGoal,
    Membership,
    Organization,
    PlannedWorkout,
    TrainingWeek,
    WorkoutAssignment,
    WorkoutLibrary,
)
from core.services_periodization import auto_periodize_athlete, suggest_cycle_pattern

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _goal(athlete, org, title, target_date, priority="A", distance_km=None):
    return AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        title=title,
        priority=priority,
        status=AthleteGoal.Status.ACTIVE,
        target_date=target_date,
        target_distance_km=distance_km,
    )


def _monday(date: datetime.date) -> datetime.date:
    return date - datetime.timedelta(days=date.weekday())


# ── Test 1: suggest_cycle_pattern distance thresholds ─────────────────────────


@pytest.mark.django_db
def test_suggest_cycle_pattern_thresholds():
    assert suggest_cycle_pattern(10) == "1:1"
    assert suggest_cycle_pattern(21) == "2:1"
    assert suggest_cycle_pattern(42) == "3:1"
    assert suggest_cycle_pattern(100) == "4:1"
    # Boundary: exactly 15 should be "1:1", 15.1 should be "2:1"
    assert suggest_cycle_pattern(15) == "1:1"
    assert suggest_cycle_pattern(15.1) == "2:1"
    # None returns default
    assert suggest_cycle_pattern(None) == "3:1"


# ── Test 2: race week gets phase="carrera" ─────────────────────────────────────


@pytest.mark.django_db
def test_race_week_gets_carrera_phase():
    org = _org("org-raceweek")
    user = _user("u-raceweek")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    race_date = datetime.date.today() + datetime.timedelta(days=21)
    _goal(athlete, org, "Champa", race_date, distance_km=42)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="3:1")

    race_monday = _monday(race_date)
    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}
    assert phases_map.get(race_monday.isoformat()) == "carrera"

    # Also verify DB
    tw = TrainingWeek.objects.get(organization=org, athlete=athlete, week_start=race_monday)
    assert tw.phase == "carrera"


# ── Test 3: taper week gets phase="descarga" ──────────────────────────────────


@pytest.mark.django_db
def test_taper_week_gets_descarga_phase():
    org = _org("org-taper")
    user = _user("u-taper")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    race_date = datetime.date.today() + datetime.timedelta(days=21)
    _goal(athlete, org, "Utacch", race_date, distance_km=42)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="3:1")

    race_monday = _monday(race_date)
    taper_monday = race_monday - datetime.timedelta(weeks=1)
    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}
    assert phases_map.get(taper_monday.isoformat()) == "descarga"


# ── Test 4: post-race week gets phase="descanso" ──────────────────────────────


@pytest.mark.django_db
def test_post_race_week_gets_descanso_phase():
    org = _org("org-postrace")
    user = _user("u-postrace")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    race_date = datetime.date.today() + datetime.timedelta(days=14)
    _goal(athlete, org, "Descanso Test", race_date, distance_km=42)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="3:1")

    race_monday = _monday(race_date)
    post_monday = race_monday + datetime.timedelta(weeks=1)
    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}
    assert phases_map.get(post_monday.isoformat()) == "descanso"


# ── Test 5: cycle 3:1 fills correctly ─────────────────────────────────────────


@pytest.mark.django_db
def test_cycle_3_1_fills_correctly():
    org = _org("org-3-1")
    user = _user("u-3-1")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    # Set race 8 weeks from now so we have enough fill weeks
    race_date = datetime.date.today() + datetime.timedelta(weeks=8)
    _goal(athlete, org, "Race 3:1", race_date, distance_km=42)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="3:1", weeks_back=8)

    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}

    race_monday = _monday(race_date)
    taper_monday = race_monday - datetime.timedelta(weeks=1)

    # Gather fill weeks (2 weeks before taper back to limit)
    fill_weeks = []
    w = taper_monday - datetime.timedelta(weeks=1)
    for _ in range(6):
        if w.isoformat() in phases_map:
            fill_weeks.append((w, phases_map[w.isoformat()]))
        w -= datetime.timedelta(weeks=1)

    # In a 3:1 cycle anchored at taper-1, positions 0,1,2=carga, 3=descarga
    # Position 0 = fill_end (closest to race)
    assert len(fill_weeks) > 0
    # Count: at most 1 in every 4 should be descarga
    carga_count = sum(1 for _, p in fill_weeks if p == "carga")
    descarga_count = sum(1 for _, p in fill_weeks if p == "descarga")
    total = carga_count + descarga_count
    if total >= 4:
        # In a 3:1 cycle: roughly 75% carga, 25% descarga
        assert carga_count / total >= 0.6


# ── Test 6: cycle 2:1 fills correctly ─────────────────────────────────────────


@pytest.mark.django_db
def test_cycle_2_1_fills_correctly():
    org = _org("org-2-1")
    user = _user("u-2-1")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    race_date = datetime.date.today() + datetime.timedelta(weeks=7)
    _goal(athlete, org, "Race 2:1", race_date, distance_km=21)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="2:1", weeks_back=7)

    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}

    race_monday = _monday(race_date)
    taper_monday = race_monday - datetime.timedelta(weeks=1)

    fill_weeks = []
    w = taper_monday - datetime.timedelta(weeks=1)
    for _ in range(5):
        if w.isoformat() in phases_map:
            fill_weeks.append((w, phases_map[w.isoformat()]))
        w -= datetime.timedelta(weeks=1)

    # 2:1 cycle: 2 carga, 1 descarga
    if len(fill_weeks) >= 3:
        carga_count = sum(1 for _, p in fill_weeks if p == "carga")
        descarga_count = sum(1 for _, p in fill_weeks if p == "descarga")
        total = carga_count + descarga_count
        assert carga_count / total >= 0.5  # at least 50% carga in 2:1


# ── Test 7: does NOT overwrite phase="lesion" ──────────────────────────────────


@pytest.mark.django_db
def test_does_not_overwrite_lesion_phase():
    org = _org("org-lesion")
    user = _user("u-lesion")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    # Pre-set a lesion week
    race_date = datetime.date.today() + datetime.timedelta(weeks=6)
    lesion_monday = _monday(race_date) - datetime.timedelta(weeks=3)
    TrainingWeek.objects.create(
        organization=org,
        athlete=athlete,
        week_start=lesion_monday,
        phase=TrainingWeek.Phase.LESION,
    )

    _goal(athlete, org, "Race Lesion", race_date, distance_km=42)

    auto_periodize_athlete(athlete, org, cycle_pattern="3:1", weeks_back=6)

    # Lesion week must remain lesion
    tw = TrainingWeek.objects.get(organization=org, athlete=athlete, week_start=lesion_monday)
    assert tw.phase == "lesion"


# ── Test 8: handles multiple goals ────────────────────────────────────────────


@pytest.mark.django_db
def test_multiple_goals_fills_between_them():
    org = _org("org-multi")
    user = _user("u-multi")
    _membership(user, org, "athlete")
    athlete = _athlete(user, org)

    race1_date = datetime.date.today() + datetime.timedelta(weeks=5)
    race2_date = datetime.date.today() + datetime.timedelta(weeks=12)

    _goal(athlete, org, "Race 1", race1_date, priority="B", distance_km=21)
    _goal(athlete, org, "Race 2", race2_date, priority="A", distance_km=42)

    result = auto_periodize_athlete(athlete, org, cycle_pattern="3:1", weeks_back=5)

    phases_map = {p["week_start"]: p["phase"] for p in result["phases"]}

    race1_monday = _monday(race1_date)
    race2_monday = _monday(race2_date)

    # Both race weeks must be "carrera"
    assert phases_map.get(race1_monday.isoformat()) == "carrera"
    assert phases_map.get(race2_monday.isoformat()) == "carrera"

    # Both taper weeks must be "descarga"
    assert phases_map.get((race1_monday - datetime.timedelta(weeks=1)).isoformat()) == "descarga"
    assert phases_map.get((race2_monday - datetime.timedelta(weeks=1)).isoformat()) == "descarga"


# ── Test 9: recent workouts detects consecutive repetition ───────────────────


@pytest.mark.django_db
def test_recent_workouts_detects_consecutive_repetition():
    org = _org("org-recent")
    coach_user = _user("coach-recent")
    athlete_user = _user("athlete-recent")
    coach_m = _membership(coach_user, org, "coach")
    athlete_m = _membership(athlete_user, org, "athlete")
    athlete = _athlete(athlete_user, org)

    lib = WorkoutLibrary.objects.create(organization=org, name="Lib")
    pw = PlannedWorkout.objects.create(
        organization=org, library=lib, name="Series 1000m",
        discipline="run", estimated_duration_seconds=3600,
    )

    today = datetime.date.today()
    today_monday = today - datetime.timedelta(days=today.weekday())

    # Assign same workout 3 consecutive weeks
    for i in range(3):
        wk = today_monday - datetime.timedelta(weeks=3 - i)
        WorkoutAssignment.objects.create(
            organization=org, athlete=athlete, planned_workout=pw,
            scheduled_date=wk + datetime.timedelta(days=2),  # Wednesday
            status="planned",
        )

    client = APIClient()
    client.force_authenticate(coach_user)
    resp = client.get(f"/api/coach/athletes/{athlete_m.pk}/recent-workouts/?weeks=6")
    assert resp.status_code == 200

    data = resp.json()
    alerts = data["repeated_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["workout"] == "Series 1000m"
    assert alerts[0]["consecutive_weeks"] >= 3


# ── Test 10: auto-periodize group endpoint ───────────────────────────────────


@pytest.mark.django_db
def test_auto_periodize_group_endpoint():
    org = _org("org-group")
    coach_user = _user("coach-group")
    coach_m = _membership(coach_user, org, "coach")

    # Athlete with a goal
    ua = _user("athlete-group-a")
    _membership(ua, org, "athlete")
    ath_a = _athlete(ua, org)
    _goal(ath_a, org, "Race Group A", datetime.date.today() + datetime.timedelta(weeks=8), distance_km=42)

    # Athlete WITHOUT a goal — should be skipped
    ub = _user("athlete-group-b")
    _membership(ub, org, "athlete")
    _athlete(ub, org)

    client = APIClient()
    client.force_authenticate(coach_user)
    resp = client.post(
        f"/api/p1/orgs/{org.pk}/auto-periodize-group/",
        {"default_cycle": "3:1"},
        format="json",
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["periodized"] >= 1
    assert data["skipped_no_goals"] >= 1

    # Athlete A should have phases created
    tw_count = TrainingWeek.objects.filter(organization=org, athlete=ath_a).count()
    assert tw_count >= 3  # at minimum: carrera + descarga (taper) + descanso
