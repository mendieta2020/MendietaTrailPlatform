"""
core/tests_pr152_athlete_view.py

Tests for PR-152: Training Volume, Wellness History, Compliance endpoints
and Readiness Score in PMC endpoints.

Tenancy: all three new endpoints are fail-closed — they require a valid coach
membership and a valid athlete membership in the same org.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    DailyLoad,
    Membership,
    Organization,
    WellnessCheckIn,
)

User = get_user_model()


@pytest.fixture
def org():
    return Organization.objects.create(name="TestOrg PR152", slug="testorg-pr152")


@pytest.fixture
def coach_user(org):
    u = User.objects.create_user(username="coach_pr152", password="x")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return u


@pytest.fixture
def athlete_user(org):
    u = User.objects.create_user(username="athlete_pr152", password="x")
    return u


@pytest.fixture
def athlete_membership(org, athlete_user):
    return Membership.objects.create(
        user=athlete_user, organization=org, role=Membership.Role.ATHLETE, is_active=True
    )


@pytest.fixture
def athlete_obj(org, athlete_user):
    return Athlete.objects.create(user=athlete_user, organization=org)


@pytest.fixture
def coach_client(coach_user):
    c = APIClient()
    c.force_authenticate(user=coach_user)
    return c


# ── Training Volume ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_training_volume_empty(coach_client, athlete_membership):
    """Returns empty buckets when athlete has no Alumno record."""
    url = f"/api/coach/athletes/{athlete_membership.pk}/training-volume/"
    res = coach_client.get(url)
    assert res.status_code == 200
    assert res.data["buckets"] == []
    assert res.data["metric"] == "distance"


@pytest.mark.django_db
def test_training_volume_invalid_metric(coach_client, athlete_membership):
    url = f"/api/coach/athletes/{athlete_membership.pk}/training-volume/?metric=badfield"
    res = coach_client.get(url)
    assert res.status_code == 400


@pytest.mark.django_db
def test_training_volume_wrong_org(athlete_membership):
    """Coach from different org cannot see athlete data."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    other_org = Organization.objects.create(name=f"OtherOrg-{uid}", slug=f"otherorg-{uid}")
    other_coach = User.objects.create_user(username=f"other_coach_{uuid.uuid4().hex[:8]}", password="x")
    Membership.objects.create(
        user=other_coach, organization=other_org, role=Membership.Role.COACH, is_active=True
    )
    c = APIClient()
    c.force_authenticate(user=other_coach)
    url = f"/api/coach/athletes/{athlete_membership.pk}/training-volume/"
    res = c.get(url)
    assert res.status_code == 404


# ── Wellness History ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_wellness_history_empty(coach_client, athlete_membership):
    """Returns empty when no Athlete/WellnessCheckIn records exist."""
    url = f"/api/coach/athletes/{athlete_membership.pk}/wellness/"
    res = coach_client.get(url)
    assert res.status_code == 200
    assert res.data["entries"] == []
    assert res.data["period_average"] is None


@pytest.mark.django_db
def test_wellness_history_with_data(coach_client, org, athlete_membership, athlete_obj):
    """Returns wellness entries when data exists."""
    from django.utils import timezone
    today = timezone.now().date()
    WellnessCheckIn.objects.create(
        athlete=athlete_obj,
        organization=org,
        date=today,
        sleep_quality=4,
        mood=3,
        energy=4,
        muscle_soreness=3,
        stress=4,
    )
    url = f"/api/coach/athletes/{athlete_membership.pk}/wellness/?days=7"
    res = coach_client.get(url)
    assert res.status_code == 200
    assert len(res.data["entries"]) == 1
    entry = res.data["entries"][0]
    assert entry["sleep"] == 4
    assert entry["mood"] == 3
    assert entry["energy"] == 4
    assert entry["soreness"] == 3
    assert entry["stress"] == 4
    assert entry["average"] == pytest.approx(3.6, abs=0.1)
    assert res.data["period_average"] is not None


# ── Compliance ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_compliance_no_plan(coach_client, athlete_membership):
    """Returns no-plan message when no WorkoutAssignments exist."""
    url = f"/api/coach/athletes/{athlete_membership.pk}/compliance/"
    res = coach_client.get(url)
    assert res.status_code == 200
    assert res.data["overall_pct"] is None
    assert res.data["buckets"] == []


# ── Readiness Score in PMC endpoint ──────────────────────────────────────────

@pytest.mark.django_db
def test_pmc_includes_readiness_score(coach_client, org, athlete_membership, athlete_user):
    """PMC endpoint includes readiness_score and readiness_label in current block."""
    from django.utils import timezone
    today = timezone.now().date()
    DailyLoad.objects.create(
        organization=org,
        athlete=athlete_user,
        date=today,
        tss=100.0,
        ctl=55.0,
        atl=65.0,
        tsb=-10.0,
        ars=45,
    )
    url = f"/api/coach/athletes/{athlete_membership.pk}/pmc/?days=7"
    res = coach_client.get(url)
    assert res.status_code == 200
    current = res.data["current"]
    assert "readiness_score" in current
    assert "readiness_label" in current
    assert 0 <= current["readiness_score"] <= 100
    assert isinstance(current["readiness_label"], str)
