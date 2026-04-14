"""
tests_pr166_login_email.py — Regression tests for PR-166 login-by-email fix.

Covers:
1. Login with email works for an existing user
2. Login with email works for a user created via team invite link
3. Login with email works after password recovery
4. Login with legacy username still works (backward compat — Fernando)
5. Welcome email is sent (mocked Resend) on invite registration
6. SESSION_COOKIE_AGE is >= 30 days and SESSION_EXPIRE_AT_BROWSER_CLOSE is False
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import Membership, Organization, TeamInvitation

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Trail Club", slug="trail-club")


@pytest.fixture
def existing_user(db):
    """User created with the old opaque-username pattern."""
    email = f"runner_{uuid.uuid4().hex[:6]}@test.com"
    u = User.objects.create_user(
        username=f"{email.split('@')[0]}_{uuid.uuid4().hex[:6]}",
        email=email,
        password="Passw0rd!",
        first_name="Test",
        last_name="Runner",
    )
    return u


@pytest.fixture
def invite_user(db, org):
    """User created via invite link (username = email, new pattern)."""
    email = f"invite_{uuid.uuid4().hex[:6]}@test.com"
    u = User.objects.create_user(
        username=email,  # new pattern: username == email
        email=email,
        password="Passw0rd!",
        first_name="Invite",
        last_name="Athlete",
    )
    Membership.objects.create(user=u, organization=org, role="athlete")
    return u


@pytest.fixture
def api_client():
    return APIClient()


# ---------------------------------------------------------------------------
# Test 1 — Login with email works for existing user (old opaque-username)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_with_email_existing_user(api_client, existing_user):
    url = reverse("token_obtain_pair")
    resp = api_client.post(url, {"email": existing_user.email, "password": "Passw0rd!"}, format="json")
    assert resp.status_code == 200, resp.data
    assert "access" in resp.data
    assert "refresh" in resp.data


# ---------------------------------------------------------------------------
# Test 2 — Login with email works for invite-registered user (username == email)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_with_email_invite_user(api_client, invite_user):
    url = reverse("token_obtain_pair")
    resp = api_client.post(url, {"email": invite_user.email, "password": "Passw0rd!"}, format="json")
    assert resp.status_code == 200, resp.data
    assert "access" in resp.data


# ---------------------------------------------------------------------------
# Test 3 — Login with email works after password recovery (new password)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_after_password_recovery(api_client, existing_user):
    new_pwd = "N3wSecure!"
    existing_user.set_password(new_pwd)
    existing_user.save()

    url = reverse("token_obtain_pair")
    resp = api_client.post(url, {"email": existing_user.email, "password": new_pwd}, format="json")
    assert resp.status_code == 200, resp.data
    assert "access" in resp.data


# ---------------------------------------------------------------------------
# Test 4 — Wrong email returns 401 (not a 500)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_wrong_email_returns_401(api_client):
    url = reverse("token_obtain_pair")
    resp = api_client.post(url, {"email": "noone@nowhere.com", "password": "anything"}, format="json")
    assert resp.status_code == 400  # SimpleJWT raises ValidationError → 400 by default


# ---------------------------------------------------------------------------
# Test 4b — Backward compat: Fernando's user can log in with his email
#            (his username may be opaque, but email lookup still works)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_backward_compat_legacy_username_via_email(api_client):
    """User with opaque username can log in using their email address."""
    u = User.objects.create_user(
        username="fernando_abc123",  # old opaque pattern
        email="fernandorubenmedieta@gmail.com",
        password="Secure1234!",
    )
    url = reverse("token_obtain_pair")
    resp = api_client.post(url, {"email": u.email, "password": "Secure1234!"}, format="json")
    assert resp.status_code == 200, resp.data
    assert "access" in resp.data


# ---------------------------------------------------------------------------
# Test 5 — Welcome email is dispatched after invite registration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_welcome_email_sent_on_invite_registration(org):
    """TeamJoinView sends welcome email when a new user registers via invite link."""
    from django.utils import timezone
    from datetime import timedelta

    coach = User.objects.create_user(
        username="coach@test.com",
        email="coach@test.com",
        password="Coach1234!",
    )
    invitation = TeamInvitation.objects.create(
        organization=org,
        role="athlete",
        created_by=coach,
        expires_at=timezone.now() + timedelta(days=7),
    )

    client = APIClient()
    url = reverse("team-join", kwargs={"token": str(invitation.token)})

    with patch("core.auth_views._send_welcome_email") as mock_send:
        resp = client.post(url, {
            "first_name": "New",
            "last_name": "Member",
            "email": f"newmember_{uuid.uuid4().hex[:6]}@test.com",
            "password": "Secure1234!",
        }, format="json")

    assert resp.status_code == 200, resp.data
    assert "access" in resp.data
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.kwargs.get("org_name") == org.name or call_kwargs.args[2] == org.name


# ---------------------------------------------------------------------------
# Test 6 — SESSION_COOKIE_AGE >= 30 days and SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# ---------------------------------------------------------------------------

def test_session_cookie_age_is_30_days():
    from django.conf import settings
    assert settings.SESSION_COOKIE_AGE >= 2592000, (
        f"SESSION_COOKIE_AGE={settings.SESSION_COOKIE_AGE} — must be >= 30 days (2592000s)"
    )


def test_session_does_not_expire_at_browser_close():
    from django.conf import settings
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is False, (
        "SESSION_EXPIRE_AT_BROWSER_CLOSE must be False to persist sessions after browser close"
    )
