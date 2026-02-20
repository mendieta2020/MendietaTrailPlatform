"""
PR11 Tests: compute_connection_status() + GET /api/connections/

Coverage:
  1. test_status_disconnected_no_credential
  2. test_status_connected_valid_token
  3. test_status_needs_reauth_expired_token
  4. test_endpoint_athlete_sees_own_status
  5. test_endpoint_cross_tenant_impossible
  6. test_endpoint_unauthenticated_returns_401

Constraints:
  - No token values asserted verbatim (only boolean checks).
  - Multi-tenant: each test uses isolated coach+alumno.
  - No mocks on business logic or tenancy.
  - Uses @pytest.mark.django_db.
"""
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Alumno, OAuthCredential


# ---------------------------------------------------------------------------
# Shared fixture (same shape as PR10's coach_and_alumno)
# ---------------------------------------------------------------------------

@pytest.fixture
def coach_and_alumno(db):
    """Minimal coach + alumno hierarchy for PR11 tests."""
    coach = User.objects.create_user(username="pr11_coach", password="x")
    user = User.objects.create_user(username="pr11_athlete", password="x")
    alumno = Alumno.objects.create(
        entrenador=coach,
        usuario=user,
        nombre="PR11",
        apellido="Athlete",
    )
    return coach, user, alumno


def _jwt(user) -> str:
    """Return a Bearer-ready JWT access token string for a user."""
    return str(RefreshToken.for_user(user).access_token)


# ---------------------------------------------------------------------------
# 1. Disconnected — no credential exists
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_status_disconnected_no_credential(coach_and_alumno):
    """
    GIVEN: No OAuthCredential exists for alumno+provider.
    WHEN:  compute_connection_status() is called.
    THEN:  Returns status="disconnected", reason_code="no_credential".
    """
    from core.oauth_credentials import compute_connection_status

    _, _, alumno = coach_and_alumno
    cs = compute_connection_status(alumno=alumno, provider="garmin")

    assert cs.status == "disconnected"
    assert cs.reason_code == "no_credential"
    assert cs.expires_at is None
    assert cs.updated_at is None


# ---------------------------------------------------------------------------
# 2. Connected — credential with non-expired (or no) expires_at
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_status_connected_valid_token(coach_and_alumno):
    """
    GIVEN: OAuthCredential exists with expires_at 1 hour in the future.
    WHEN:  compute_connection_status() is called.
    THEN:  Returns status="connected", reason_code="".

    Also tested: expires_at=None → also "connected" (no expiry = no constraint).
    """
    from core.oauth_credentials import compute_connection_status

    _, _, alumno = coach_and_alumno
    future_expires = timezone.now() + timezone.timedelta(hours=1)

    OAuthCredential.objects.create(
        alumno=alumno,
        provider="coros",
        external_user_id="coros-uid-pr11",
        access_token="tok-valid",
        expires_at=future_expires,
    )

    cs = compute_connection_status(alumno=alumno, provider="coros")

    assert cs.status == "connected"
    assert cs.reason_code == ""
    assert cs.expires_at is not None
    assert cs.updated_at is not None


@pytest.mark.django_db
def test_status_connected_no_expiry(coach_and_alumno):
    """
    GIVEN: OAuthCredential exists with expires_at=None.
    WHEN:  compute_connection_status() is called.
    THEN:  Returns status="connected" (None expiry → treated as non-expiring).
    """
    from core.oauth_credentials import compute_connection_status

    _, _, alumno = coach_and_alumno

    OAuthCredential.objects.create(
        alumno=alumno,
        provider="suunto",
        external_user_id="suunto-uid-pr11",
        access_token="tok-no-expiry",
        expires_at=None,
    )

    cs = compute_connection_status(alumno=alumno, provider="suunto")

    assert cs.status == "connected"
    assert cs.reason_code == ""
    assert cs.expires_at is None


# ---------------------------------------------------------------------------
# 3. Needs reauth — token expired
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_status_needs_reauth_expired_token(coach_and_alumno):
    """
    GIVEN: OAuthCredential exists with expires_at 1 second in the past.
    WHEN:  compute_connection_status() is called.
    THEN:  Returns status="needs_reauth", reason_code="token_expired".
    """
    from core.oauth_credentials import compute_connection_status

    _, _, alumno = coach_and_alumno
    past_expires = timezone.now() - timezone.timedelta(seconds=1)

    OAuthCredential.objects.create(
        alumno=alumno,
        provider="polar",
        external_user_id="polar-uid-pr11",
        access_token="tok-expired",
        expires_at=past_expires,
    )

    cs = compute_connection_status(alumno=alumno, provider="polar")

    assert cs.status == "needs_reauth"
    assert cs.reason_code == "token_expired"
    assert cs.expires_at is not None
    assert cs.updated_at is not None


# ---------------------------------------------------------------------------
# 4. Endpoint: athlete sees own status
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_endpoint_athlete_sees_own_status(client, coach_and_alumno):
    """
    GIVEN: Authenticated athlete with a connected garmin credential.
    WHEN:  GET /api/connections/?provider=garmin
    THEN:  200 + correct alumno_id + status="connected".
    """
    _, user, alumno = coach_and_alumno

    OAuthCredential.objects.create(
        alumno=alumno,
        provider="garmin",
        external_user_id="garmin-uid-pr11",
        access_token="tok-endpoint",
        expires_at=timezone.now() + timezone.timedelta(hours=2),
    )

    response = client.get(
        "/api/connections/?provider=garmin",
        HTTP_AUTHORIZATION=f"Bearer {_jwt(user)}",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "garmin"
    assert data["status"] == "connected"
    assert data["alumno_id"] == alumno.pk
    assert data["reason_code"] == ""
    # Tokens must NOT appear in the response
    assert "access_token" not in data
    assert "refresh_token" not in data


# ---------------------------------------------------------------------------
# 5. Cross-tenant: athlete cannot see another athlete's data
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_endpoint_cross_tenant_impossible(client, db):
    """
    GIVEN: Two athletes (A with garmin connected, B with nothing).
    WHEN:  Athlete B requests GET /api/connections/?provider=garmin
    THEN:  B sees "disconnected" (their own status), NOT A's data.

    Tenancy is enforced by: alumno = Alumno.objects.get(usuario=request.user).
    No alumno_id parameter is accepted by the endpoint — leak is structurally impossible.
    """
    coach = User.objects.create_user(username="pr11_cross_coach", password="x")

    # Athlete A: has garmin connected
    user_a = User.objects.create_user(username="pr11_athlete_a", password="x")
    alumno_a = Alumno.objects.create(entrenador=coach, usuario=user_a, nombre="A", apellido="PR11")
    OAuthCredential.objects.create(
        alumno=alumno_a,
        provider="garmin",
        external_user_id="garmin-uid-a",
        access_token="tok-a",
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    # Athlete B: no credentials
    user_b = User.objects.create_user(username="pr11_athlete_b", password="x")
    Alumno.objects.create(entrenador=coach, usuario=user_b, nombre="B", apellido="PR11")

    # B requests the endpoint (cannot pass alumno_id)
    response = client.get(
        "/api/connections/?provider=garmin",
        HTTP_AUTHORIZATION=f"Bearer {_jwt(user_b)}",
    )

    assert response.status_code == 200
    data = response.json()
    # B sees their own status (disconnected), NOT A's
    assert data["status"] == "disconnected"
    assert data["reason_code"] == "no_credential"
    # No leakage of A's data
    assert "garmin-uid-a" not in str(data)
    assert "tok-a" not in str(data)


# ---------------------------------------------------------------------------
# 6. Unauthenticated → 401
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_endpoint_unauthenticated_returns_401(client):
    """
    GIVEN: No Authorization header.
    WHEN:  GET /api/connections/
    THEN:  401 Unauthorized.
    """
    response = client.get("/api/connections/")
    assert response.status_code == 401
