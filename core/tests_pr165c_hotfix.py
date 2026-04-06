"""
PR-165c Hotfix: Coach profile, auto-create, athlete coach assignment, plan toggle.
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from core.models import Coach, Membership, Organization, TeamInvitation

User = get_user_model()


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org", slug="test-org")


@pytest.fixture
def owner_user(db, org):
    u = User.objects.create_user(username="owner", email="owner@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role="owner", is_active=True)
    return u


@pytest.fixture
def coach_user(db, org):
    u = User.objects.create_user(username="coach1", email="coach1@test.com", password="pw")
    return u


@pytest.fixture
def api_client():
    return APIClient()


# ── Fix 1.1: Auto-create Coach record on TeamJoin ────────────────────────────

@pytest.mark.django_db
def test_team_join_creates_coach_record(api_client, org, owner_user, coach_user):
    """When a user accepts a team invitation with role='coach', Coach record is auto-created."""
    inv = TeamInvitation.objects.create(
        organization=org,
        email=coach_user.email,
        role="coach",
        created_by=owner_user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    api_client.force_authenticate(user=coach_user)
    url = f"/api/team-join/{inv.token}/"
    response = api_client.post(url)
    assert response.status_code == 200
    assert Coach.objects.filter(user=coach_user, organization=org).exists(), (
        "Coach record should be auto-created when joining via team invite with role='coach'"
    )


@pytest.mark.django_db
def test_team_join_coach_idempotent(api_client, org, owner_user, coach_user):
    """Accepting a second invitation does not create duplicate Coach records."""
    # Pre-create the Coach record
    Coach.objects.create(user=coach_user, organization=org, is_active=True)
    inv = TeamInvitation.objects.create(
        organization=org,
        email=coach_user.email,
        role="coach",
        created_by=owner_user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    api_client.force_authenticate(user=coach_user)
    url = f"/api/team-join/{inv.token}/"
    api_client.post(url)
    assert Coach.objects.filter(user=coach_user, organization=org).count() == 1


# ── Fix 1.3: MyCoachProfileView GET/PATCH ───────────────────────────────────

@pytest.mark.django_db
def test_my_coach_profile_get(api_client, org, coach_user):
    """GET /api/me/coach-profile/ returns coach profile fields."""
    Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)
    Coach.objects.create(
        user=coach_user, organization=org, is_active=True,
        bio="Trail specialist", specialties="Ultra", years_experience=5,
    )
    api_client.force_authenticate(user=coach_user)
    url = f"/api/me/coach-profile/?org_id={org.pk}"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data["bio"] == "Trail specialist"
    assert response.data["specialties"] == "Ultra"
    assert response.data["years_experience"] == 5


@pytest.mark.django_db
def test_my_coach_profile_patch(api_client, org, coach_user):
    """PATCH /api/me/coach-profile/ updates coach profile fields."""
    Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)
    Coach.objects.create(user=coach_user, organization=org, is_active=True)
    api_client.force_authenticate(user=coach_user)
    url = "/api/me/coach-profile/"
    response = api_client.patch(url, {"org_id": org.pk, "bio": "Updated bio", "years_experience": 8}, format="json")
    assert response.status_code == 200
    coach = Coach.objects.get(user=coach_user, organization=org)
    assert coach.bio == "Updated bio"
    assert coach.years_experience == 8


@pytest.mark.django_db
def test_my_coach_profile_not_found(api_client, org, owner_user):
    """GET returns 404 when user has no Coach record in the org."""
    api_client.force_authenticate(user=owner_user)
    url = f"/api/me/coach-profile/?org_id={org.pk}"
    response = api_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_my_coach_profile_cannot_access_other_org(api_client, coach_user):
    """Coach cannot retrieve a profile from an org they don't belong to."""
    org1 = Organization.objects.create(name="Org1", slug="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2")
    Coach.objects.create(user=coach_user, organization=org1, is_active=True)
    api_client.force_authenticate(user=coach_user)
    url = f"/api/me/coach-profile/?org_id={org2.pk}"
    response = api_client.get(url)
    assert response.status_code == 404
