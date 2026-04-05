"""
PR-165a — TeamInvitation backend tests.

Covers:
- TeamInvitation model: creation, expiry check, str
- Create invitation: owner can create, coach cannot, athlete cannot
- List invitations: org-scoped, only owner/coach sees them
- Accept invitation: creates user + membership with correct role
- Accept invitation: expired token rejected
- Accept invitation: already-accepted token rejected
- Accept invitation: email mismatch rejected (when email is set)
- Tenancy: invitation from org A cannot create membership in org B (token isolation)
"""
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import (
    Membership,
    Organization,
    TeamInvitation,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email=None, password="testpass"):
    email = email or f"{username}@example.com"
    return User.objects.create_user(username=username, email=email, password=password)


def _membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role)


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


def _invitation(org, role="coach", email="", days=7, status=TeamInvitation.Status.PENDING, creator=None):
    return TeamInvitation.objects.create(
        organization=org,
        role=role,
        email=email,
        status=status,
        created_by=creator,
        expires_at=timezone.now() + timedelta(days=days),
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_creation_defaults():
    org = _org("model-org")
    owner = _user("model-owner")
    inv = _invitation(org, role="coach", creator=owner)
    assert inv.token is not None
    assert inv.status == TeamInvitation.Status.PENDING
    assert not inv.is_expired


@pytest.mark.django_db
def test_model_is_expired_true():
    org = _org("expired-org")
    inv = _invitation(org, days=-1)
    assert inv.is_expired


@pytest.mark.django_db
def test_model_str():
    org = _org("str-org")
    inv = _invitation(org, role="staff")
    assert "TeamInvite" in str(inv)
    assert "staff" in str(inv)
    assert "str-org" in str(inv)


# ---------------------------------------------------------------------------
# Create invitation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_create_invitation():
    org = _org("owner-org")
    owner = _user("owner-user")
    _membership(owner, org, "owner")
    client = _auth_client(owner)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "coach"})
    assert resp.status_code == status.HTTP_201_CREATED
    assert "token" in resp.data
    assert "join_url" in resp.data
    assert resp.data["role"] == "coach"


@pytest.mark.django_db
def test_owner_can_create_staff_invitation():
    org = _org("owner-staff-org")
    owner = _user("owner-staff-user")
    _membership(owner, org, "owner")
    client = _auth_client(owner)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "staff"})
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["role"] == "staff"


@pytest.mark.django_db
def test_coach_cannot_create_invitation():
    org = _org("coach-create-org")
    owner = _user("coach-owner")
    coach_user = _user("coach-user-c")
    _membership(owner, org, "owner")
    _membership(coach_user, org, "coach")
    client = _auth_client(coach_user)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "coach"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_athlete_cannot_create_invitation():
    org = _org("athlete-create-org")
    owner = _user("ath-owner")
    ath_user = _user("ath-user-c")
    _membership(owner, org, "owner")
    _membership(ath_user, org, "athlete")
    client = _auth_client(ath_user)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "coach"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_cannot_invite_with_owner_role():
    org = _org("owner-role-org")
    owner = _user("owner-role-user")
    _membership(owner, org, "owner")
    client = _auth_client(owner)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "owner"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cannot_invite_with_athlete_role():
    org = _org("ath-role-org")
    owner = _user("ath-role-owner")
    _membership(owner, org, "owner")
    client = _auth_client(owner)

    resp = client.post(f"/api/p1/orgs/{org.id}/invitations/team/", {"role": "athlete"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# List invitations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_list_invitations():
    org = _org("list-org")
    owner = _user("list-owner")
    _membership(owner, org, "owner")
    _invitation(org, creator=owner)
    _invitation(org, role="staff", creator=owner)
    client = _auth_client(owner)

    resp = client.get(f"/api/p1/orgs/{org.id}/invitations/team/")
    assert resp.status_code == status.HTTP_200_OK
    results = resp.data.get("results", resp.data)
    assert len(results) == 2


@pytest.mark.django_db
def test_list_is_org_scoped():
    """Invitations from another org must not appear."""
    org_a = _org("list-org-a")
    org_b = _org("list-org-b")
    owner_a = _user("list-owner-a")
    owner_b = _user("list-owner-b")
    _membership(owner_a, org_a, "owner")
    _membership(owner_b, org_b, "owner")
    _invitation(org_b, creator=owner_b)
    client = _auth_client(owner_a)

    resp = client.get(f"/api/p1/orgs/{org_a.id}/invitations/team/")
    assert resp.status_code == status.HTTP_200_OK
    results = resp.data.get("results", resp.data)
    assert len(results) == 0


@pytest.mark.django_db
def test_athlete_cannot_list_invitations():
    org = _org("ath-list-org")
    owner = _user("ath-list-owner")
    ath = _user("ath-list-ath")
    _membership(owner, org, "owner")
    _membership(ath, org, "athlete")
    client = _auth_client(ath)

    resp = client.get(f"/api/p1/orgs/{org.id}/invitations/team/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Accept invitation (TeamJoinView)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_team_join_info():
    org = _org("join-info-org")
    inv = _invitation(org, role="coach")
    client = APIClient()

    resp = client.get(f"/api/team-join/{inv.token}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["role"] == "coach"
    assert resp.data["org_name"] == "join-info-org"


@pytest.mark.django_db
def test_accept_creates_user_and_membership():
    org = _org("accept-org")
    inv = _invitation(org, role="coach")
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv.token}/", {
        "first_name": "Juan",
        "last_name": "Coach",
        "email": "juan@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == status.HTTP_200_OK
    assert "access" in resp.data

    user = User.objects.get(email="juan@example.com")
    assert Membership.objects.filter(user=user, organization=org, role="coach").exists()

    inv.refresh_from_db()
    assert inv.status == TeamInvitation.Status.ACCEPTED
    assert inv.accepted_by == user


@pytest.mark.django_db
def test_accept_expired_token_rejected():
    org = _org("expired-accept-org")
    inv = _invitation(org, role="coach", days=-1)
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv.token}/", {
        "email": "expired@example.com",
        "password": "pass",
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "expired"


@pytest.mark.django_db
def test_accept_already_accepted_rejected():
    org = _org("already-accepted-org")
    inv = _invitation(org, role="coach", status=TeamInvitation.Status.ACCEPTED)
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv.token}/", {
        "email": "used@example.com",
        "password": "pass",
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "already_used"


@pytest.mark.django_db
def test_accept_email_mismatch_rejected():
    org = _org("email-mismatch-org")
    inv = _invitation(org, role="coach", email="allowed@example.com")
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv.token}/", {
        "email": "wrong@example.com",
        "password": "pass123",
        "first_name": "X",
        "last_name": "Y",
    })
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "email_mismatch"


@pytest.mark.django_db
def test_accept_email_match_succeeds():
    org = _org("email-match-org")
    inv = _invitation(org, role="staff", email="correct@example.com")
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv.token}/", {
        "email": "correct@example.com",
        "password": "pass123",
        "first_name": "X",
        "last_name": "Y",
    })
    assert resp.status_code == status.HTTP_200_OK
    assert Membership.objects.filter(
        user__email="correct@example.com", organization=org, role="staff"
    ).exists()


@pytest.mark.django_db
def test_get_invalid_token_returns_404():
    client = APIClient()
    fake_token = uuid.uuid4()
    resp = client.get(f"/api/team-join/{fake_token}/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.data["code"] == "not_found"


# ---------------------------------------------------------------------------
# Tenancy isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_invitation_token_is_org_isolated():
    """
    Org B's invitation token cannot create membership in Org A.
    Each token is self-contained and points to its own organization.
    """
    org_a = _org("iso-org-a")
    org_b = _org("iso-org-b")
    inv_b = _invitation(org_b, role="coach")
    client = APIClient()

    resp = client.post(f"/api/team-join/{inv_b.token}/", {
        "email": "iso@example.com",
        "password": "pass123",
        "first_name": "X",
        "last_name": "Y",
    })
    assert resp.status_code == status.HTTP_200_OK

    user = User.objects.get(email="iso@example.com")
    # Must only have membership in org_b — never in org_a
    assert Membership.objects.filter(user=user, organization=org_b).exists()
    assert not Membership.objects.filter(user=user, organization=org_a).exists()


# ---------------------------------------------------------------------------
# Fix 4: Delete / revoke invitation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_delete_pending_invitation():
    org = _org("del-org")
    owner = _user("del-owner")
    _membership(owner, org, "owner")
    inv = _invitation(org, creator=owner)
    client = _auth_client(owner)

    resp = client.delete(f"/api/p1/orgs/{org.id}/invitations/team/{inv.id}/")
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert not TeamInvitation.objects.filter(id=inv.id).exists()


@pytest.mark.django_db
def test_non_owner_cannot_delete_invitation():
    org = _org("del-perm-org")
    owner = _user("del-perm-owner")
    coach_user = _user("del-perm-coach")
    _membership(owner, org, "owner")
    _membership(coach_user, org, "coach")
    inv = _invitation(org, creator=owner)
    client = _auth_client(coach_user)

    resp = client.delete(f"/api/p1/orgs/{org.id}/invitations/team/{inv.id}/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert TeamInvitation.objects.filter(id=inv.id).exists()


@pytest.mark.django_db
def test_cannot_delete_accepted_invitation():
    org = _org("del-accepted-org")
    owner = _user("del-accepted-owner")
    _membership(owner, org, "owner")
    inv = _invitation(org, status=TeamInvitation.Status.ACCEPTED, creator=owner)
    client = _auth_client(owner)

    resp = client.delete(f"/api/p1/orgs/{org.id}/invitations/team/{inv.id}/")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert TeamInvitation.objects.filter(id=inv.id).exists()
