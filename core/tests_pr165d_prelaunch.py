"""
PR-165d Pre-launch blockers: tenancy, profile saves, delete-plan protection, email exists.
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
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org A1", slug="test-org-a1")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Org", slug="other-org")


@pytest.fixture
def owner_user(db, org):
    u = User.objects.create_user(username="owner165d", email="owner165d@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.OWNER, is_active=True)
    return u


@pytest.fixture
def coach_a(db, org):
    u = User.objects.create_user(username="coachA165d", email="coachA@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return Coach.objects.create(user=u, organization=org)


@pytest.fixture
def coach_b(db, org):
    u = User.objects.create_user(username="coachB165d", email="coachB@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return Coach.objects.create(user=u, organization=org)


@pytest.fixture
def athlete_for_a(db, org, coach_a):
    u = User.objects.create_user(username="ath_a165d", email="ath_a@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.ATHLETE, is_active=True)
    a = Athlete.objects.create(user=u, organization=org)
    AthleteCoachAssignment.objects.create(athlete=a, coach=coach_a, organization=org)
    return a


@pytest.fixture
def athlete_for_b(db, org, coach_b):
    u = User.objects.create_user(username="ath_b165d", email="ath_b@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.ATHLETE, is_active=True)
    a = Athlete.objects.create(user=u, organization=org)
    AthleteCoachAssignment.objects.create(athlete=a, coach=coach_b, organization=org)
    return a


# ---------------------------------------------------------------------------
# A.1 — Coach dashboard tenancy: coach only sees their own athletes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_coach_briefing_only_shows_own_athletes(org, coach_a, coach_b, athlete_for_a, athlete_for_b):
    """Coach A must NOT see athlete assigned to Coach B in the briefing athlete count."""
    client = APIClient()
    client.force_authenticate(user=coach_a.user)

    url = f"/api/p1/orgs/{org.pk}/coach-briefing/"
    res = client.get(url)

    assert res.status_code == 200
    # Coach A has 1 athlete; should not see Coach B's athlete
    assert res.data["athletes_total"] == 1


@pytest.mark.django_db
def test_owner_briefing_sees_all_athletes(org, owner_user, coach_a, coach_b, athlete_for_a, athlete_for_b):
    """Owner must see ALL athletes (both assigned to different coaches)."""
    client = APIClient()
    client.force_authenticate(user=owner_user)

    url = f"/api/p1/orgs/{org.pk}/coach-briefing/"
    res = client.get(url)

    assert res.status_code == 200
    assert res.data["athletes_total"] == 2


# ---------------------------------------------------------------------------
# A.3 / A.6 — Profile save and refetch
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_my_user_profile_get_and_patch(org, owner_user):
    """Owner can read and update their own first_name/last_name via /api/me/user/."""
    client = APIClient()
    client.force_authenticate(user=owner_user)

    res = client.patch("/api/me/user/", {"first_name": "Fernando", "last_name": "Mendieta"}, format="json")
    assert res.status_code == 200
    assert res.data["first_name"] == "Fernando"
    assert res.data["last_name"] == "Mendieta"

    get_res = client.get("/api/me/user/")
    assert get_res.status_code == 200
    assert get_res.data["first_name"] == "Fernando"


@pytest.mark.django_db
def test_my_staff_profile_save_and_refetch(db, org):
    """Staff can save and retrieve their profile via /api/me/staff-profile/."""
    u = User.objects.create_user(username="staff165d", email="staff@test.com", password="pw")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.STAFF, is_active=True,
                              staff_title="")

    client = APIClient()
    client.force_authenticate(user=u)

    res = client.patch(
        "/api/me/staff-profile/",
        {"org_id": org.pk, "staff_title": "Coordinadora", "phone": "+54 911 1234"},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["staff_title"] == "Coordinadora"

    get_res = client.get(f"/api/me/staff-profile/?org_id={org.pk}")
    assert get_res.status_code == 200
    assert get_res.data["staff_title"] == "Coordinadora"


@pytest.mark.django_db
def test_my_staff_profile_patch_with_birth_date_returns_isoformat(db, org):
    """Regression: PATCH with birth_date must not crash on .isoformat() in response.

    Django does not auto-convert string assignments on DateField in-memory; without
    refresh_from_db() the in-memory attribute remains a str and .isoformat() raises
    AttributeError. See Sentry PYTHON-DJANGO-6.
    """
    u = User.objects.create_user(
        username="staffbd", email="staffbd@test.com", password="pw"
    )
    Membership.objects.create(
        user=u, organization=org, role=Membership.Role.STAFF,
        is_active=True, staff_title="",
    )
    client = APIClient()
    client.force_authenticate(user=u)

    res = client.patch(
        "/api/me/staff-profile/",
        {"org_id": org.pk, "birth_date": "1995-03-15"},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["birth_date"] == "1995-03-15"


# ---------------------------------------------------------------------------
# B.3 — Delete plan with active subscriptions must fail 400
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_delete_plan_with_active_subscriptions_returns_400(org, owner_user):
    """Deleting a plan with active athlete subscriptions must return 400."""
    from core.models import AthleteSubscription

    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan Test", price_ars=1000, is_active=True
    )
    athlete_user = User.objects.create_user(username="subath165d", email="subath@test.com", password="pw")
    Membership.objects.create(user=athlete_user, organization=org, role=Membership.Role.ATHLETE, is_active=True)
    athlete = Athlete.objects.create(user=athlete_user, organization=org)
    AthleteSubscription.objects.create(
        athlete=athlete, organization=org, coach_plan=plan,
        status=AthleteSubscription.Status.ACTIVE,
    )

    client = APIClient()
    client.force_authenticate(user=owner_user)
    res = client.delete(f"/api/billing/plans/{plan.pk}/")
    assert res.status_code == 400
    assert "suscripto" in res.data["detail"].lower()


@pytest.mark.django_db
def test_delete_plan_without_active_subscriptions_succeeds(org, owner_user):
    """Deleting a plan with no active subscriptions must succeed."""
    plan = CoachPricingPlan.objects.create(
        organization=org, name="Plan Empty", price_ars=500, is_active=True
    )
    client = APIClient()
    client.force_authenticate(user=owner_user)
    res = client.delete(f"/api/billing/plans/{plan.pk}/")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# B.1 — Registration with existing email returns recovery hint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_register_existing_email_returns_recovery_hint(db):
    """Registering with an existing email must return code=email_exists and a login_url."""
    User.objects.create_user(username="existing165d", email="taken@test.com", password="pw")

    client = APIClient()
    res = client.post(
        "/api/auth/register/",
        {"email": "taken@test.com", "password": "newpassword123", "first_name": "X", "last_name": "Y"},
        format="json",
    )
    assert res.status_code == 400
    assert res.data.get("code") == "email_exists"
    assert res.data.get("login_url") == "/login"
