"""
PR-165e Final pre-launch: password recovery, athletes tenancy, coach profile GET, plan delete.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteCoachAssignment,
    Coach,
    CoachPricingPlan,
    Membership,
    Organization,
    PasswordResetToken,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org165e", slug="org-165e")


@pytest.fixture
def owner(db, org):
    u = User.objects.create_user(username="owner165e", email="owner165e@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.OWNER, is_active=True)
    return u


@pytest.fixture
def coach(db, org):
    u = User.objects.create_user(username="coach165e", email="coach165e@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return Coach.objects.create(user=u, organization=org)


@pytest.fixture
def other_coach(db, org):
    u = User.objects.create_user(username="other_coach165e", email="other_coach165e@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return Coach.objects.create(user=u, organization=org)


@pytest.fixture
def athlete_assigned(db, org, coach):
    u = User.objects.create_user(username="ath_assigned165e", email="ath_a165e@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.ATHLETE, is_active=True)
    a = Athlete.objects.create(user=u, organization=org)
    AthleteCoachAssignment.objects.create(athlete=a, coach=coach, organization=org)
    return a


@pytest.fixture
def athlete_other(db, org, other_coach):
    u = User.objects.create_user(username="ath_other165e", email="ath_b165e@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.ATHLETE, is_active=True)
    a = Athlete.objects.create(user=u, organization=org)
    AthleteCoachAssignment.objects.create(athlete=a, coach=other_coach, organization=org)
    return a


def _results(res_data):
    """Unwrap paginated or plain list response."""
    if isinstance(res_data, dict) and "results" in res_data:
        return res_data["results"]
    return res_data


# ---------------------------------------------------------------------------
# Group 1 — Password reset request: anti-enumeration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_password_reset_request_existing_user_returns_200(owner):
    """Requesting reset for an existing email must return 200 (not 404)."""
    client = APIClient()
    res = client.post("/api/auth/password-reset/request/", {"email": owner.email}, format="json")
    assert res.status_code == 200


@pytest.mark.django_db
def test_password_reset_request_nonexistent_email_returns_200(db):
    """Requesting reset for a non-existent email must also return 200 (anti-enumeration)."""
    client = APIClient()
    res = client.post("/api/auth/password-reset/request/", {"email": "nobody@nowhere.com"}, format="json")
    assert res.status_code == 200


@pytest.mark.django_db
def test_password_reset_confirm_valid_token(owner):
    """Valid token + new password succeeds and invalidates the token."""
    raw_token = PasswordResetToken.create_for_user(owner)

    client = APIClient()
    res = client.post(
        "/api/auth/password-reset/confirm/",
        {"token": raw_token, "new_password": "NewSecure123!"},
        format="json",
    )
    assert res.status_code == 200

    # Token is consumed — second use must fail
    res2 = client.post(
        "/api/auth/password-reset/confirm/",
        {"token": raw_token, "new_password": "AnotherPwd456!"},
        format="json",
    )
    assert res2.status_code == 400


@pytest.mark.django_db
def test_password_reset_confirm_invalid_token(db):
    """Invalid token must return 400."""
    client = APIClient()
    res = client.post(
        "/api/auth/password-reset/confirm/",
        {"token": "totallyinvalidtoken", "new_password": "NewPwd123!"},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_password_reset_token_is_single_use(owner):
    """Token consumed once cannot be reused."""
    raw_token = PasswordResetToken.create_for_user(owner)
    consumed_user = PasswordResetToken.consume(raw_token)
    assert consumed_user is not None
    assert consumed_user.pk == owner.pk

    # Second consume must return None
    assert PasswordResetToken.consume(raw_token) is None


# ---------------------------------------------------------------------------
# Group 2 — Athletes tenancy: coach only sees assigned athletes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_coach_only_sees_assigned_athletes_in_roster(
    org, coach, athlete_assigned, athlete_other
):
    """GET /api/p1/orgs/<id>/roster/athletes/ for a coach must only return their assigned athletes."""
    client = APIClient()
    client.force_authenticate(user=coach.user)

    res = client.get(f"/api/p1/orgs/{org.pk}/roster/athletes/")
    assert res.status_code == 200

    items = _results(res.data)
    returned_ids = {a["id"] for a in items}
    assert athlete_assigned.pk in returned_ids
    assert athlete_other.pk not in returned_ids


@pytest.mark.django_db
def test_owner_sees_all_athletes_in_roster(
    org, owner, athlete_assigned, athlete_other
):
    """Owner must see ALL athletes regardless of assignment."""
    client = APIClient()
    client.force_authenticate(user=owner)

    res = client.get(f"/api/p1/orgs/{org.pk}/roster/athletes/")
    assert res.status_code == 200

    items = _results(res.data)
    returned_ids = {a["id"] for a in items}
    assert athlete_assigned.pk in returned_ids
    assert athlete_other.pk in returned_ids


# ---------------------------------------------------------------------------
# Group 3 — Coach profile GET includes contact fields
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_coach_profile_get_includes_contact_fields(org, coach):
    """GET /api/me/coach-profile/ must include phone, birth_date, photo_url, instagram."""
    client = APIClient()
    client.force_authenticate(user=coach.user)

    # First PATCH to set some contact fields
    client.patch(
        "/api/me/coach-profile/",
        {"org_id": org.pk, "phone": "+54 911 9999", "instagram": "testcoach"},
        format="json",
    )

    res = client.get(f"/api/me/coach-profile/?org_id={org.pk}")
    assert res.status_code == 200
    assert "phone" in res.data
    assert "birth_date" in res.data
    assert "photo_url" in res.data
    assert "instagram" in res.data
    assert res.data["phone"] == "+54 911 9999"
    assert res.data["instagram"] == "testcoach"


# ---------------------------------------------------------------------------
# Group 4 — Delete plan with no active subscriptions succeeds
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_delete_plan_with_no_active_subs_succeeds(org, owner):
    """Deleting a plan with zero active subscriptions must return 200 or 204."""
    plan = CoachPricingPlan.objects.create(
        organization=org,
        name="Test Plan 165e",
        price_ars=1000,
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=owner)

    res = client.delete(f"/api/billing/plans/{plan.pk}/")
    assert res.status_code in (200, 204)
