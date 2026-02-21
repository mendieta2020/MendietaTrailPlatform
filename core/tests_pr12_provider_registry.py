"""
PR12 Tests: Provider Registry (Single Source of Truth)

1) test_supported_providers_constant_exists
2) test_connections_endpoint_returns_all_supported_providers
3) test_invalid_provider_returns_400
"""
import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Alumno
from core.providers import SUPPORTED_PROVIDERS


@pytest.fixture
def coach_and_alumno(db):
    """Minimal coach + alumno hierarchy for PR12 tests."""
    coach = User.objects.create_user(username="pr12_coach", password="x")
    user = User.objects.create_user(username="pr12_athlete", password="x")
    alumno = Alumno.objects.create(
        entrenador=coach,
        usuario=user,
        nombre="PR12",
        apellido="Athlete",
    )
    return coach, user, alumno


def _jwt(user) -> str:
    """Return a Bearer-ready JWT access token string for a user."""
    return str(RefreshToken.for_user(user).access_token)


# ---------------------------------------------------------------------------
# 1. Constant exists and has 5 providers
# ---------------------------------------------------------------------------
def test_supported_providers_constant_exists():
    """
    Verify that SUPPORTED_PROVIDERS exists and contains the 5 expected providers.
    It serves as the single source of truth for the platform.
    """
    assert isinstance(SUPPORTED_PROVIDERS, list)
    assert len(SUPPORTED_PROVIDERS) == 5
    
    expected = {"strava", "garmin", "coros", "suunto", "polar"}
    assert set(SUPPORTED_PROVIDERS) == expected


# ---------------------------------------------------------------------------
# 2. Endpoint returns exactly len(SUPPORTED_PROVIDERS)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_connections_endpoint_returns_all_supported_providers(client, coach_and_alumno):
    """
    GIVEN: Authenticated athlete.
    WHEN:  GET /api/connections/ (without ?provider= param)
    THEN:  Returns exactly len(SUPPORTED_PROVIDERS) connections.
    """
    _, user, _ = coach_and_alumno
    
    response = client.get(
        "/api/connections/",
        HTTP_AUTHORIZATION=f"Bearer {_jwt(user)}",
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Assert returning exactly the same length
    assert "connections" in data
    assert len(data["connections"]) == len(SUPPORTED_PROVIDERS)
    
    # Assert all supported providers are represented
    returned_providers = {c["provider"] for c in data["connections"]}
    assert returned_providers == set(SUPPORTED_PROVIDERS)


# ---------------------------------------------------------------------------
# 3. Invalid provider returns 400
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_invalid_provider_returns_400(client, coach_and_alumno):
    """
    GIVEN: Authenticated athlete.
    WHEN:  GET /api/connections/?provider=invalid
    THEN:  Returns 400 with a controlled error message pointing to the registry.
    """
    _, user, _ = coach_and_alumno
    
    response = client.get(
        "/api/connections/?provider=invalid",
        HTTP_AUTHORIZATION=f"Bearer {_jwt(user)}",
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_provider"
    assert "supported_providers" in data
    assert data["supported_providers"] == SUPPORTED_PROVIDERS
