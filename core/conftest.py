"""
Pytest configuration and fixtures for OAuth integration tests.

Provides:
- Auto-cleanup of test data (prevents orphaned ExternalIdentity/OAuthIntegrationStatus)
- Shared fixtures for creating test users/athletes
"""
import pytest
from django.conf import settings


@pytest.fixture(scope="function", autouse=True)
def cleanup_oauth_test_data(db):
    """
    Auto-cleanup fixture: remove orphaned records after each test.
    
    This prevents test pollution where failed tests leave behind:
    - ExternalIdentity with alumno_id=None (orphaned)
    - OAuthIntegrationStatus with error_reason from test mocks
    
    Runs automatically after EVERY test function.
    """
    # Run test first
    yield
    
    # Cleanup after test completes
    from core.models import ExternalIdentity
    from core.integration_models import OAuthIntegrationStatus
    
    # Delete orphaned ExternalIdentity (no linked alumno)
    deleted_identities_count, _ = ExternalIdentity.objects.filter(alumno__isnull=True).delete()
    
    # Delete test-generated failed OAuthIntegrationStatus
    # (These come from mocked signal tests where uid parsing fails)
    deleted_statuses_count, _ = OAuthIntegrationStatus.objects.filter(
        error_reason__in=[
            "exception_during_link",
            "missing_athlete_id", 
            "missing_access_token",
        ]
    ).delete()
    
    # Optional: log cleanup (helpful for debugging test pollution)
    if deleted_identities_count > 0 or deleted_statuses_count > 0:
        print(
            f"\n🧹 [CLEANUP] "
            f"Removed {deleted_identities_count} orphaned ExternalIdentity, "
            f"{deleted_statuses_count} failed OAuthIntegrationStatus"
        )


@pytest.fixture
def test_athlete(db):
    """
    Create a test athlete (User + Alumno + Coach) for OAuth tests.
    
    Returns:
        tuple: (user, alumno, coach_user)
    """
    from core.models import Alumno, User
    
    coach_user = User.objects.create_user(username="test_coach", password="testpass")
    user = User.objects.create_user(username="test_athlete", password="testpass")
    alumno = Alumno.objects.create(
        usuario=user,
        entrenador=coach_user,
        nombre="Test Athlete",
    )
    
    return user, alumno, coach_user


@pytest.fixture
def authenticated_client(client, test_athlete):
    """
    Create an authenticated API client for a test athlete.
    
    Returns:
        tuple: (client, user, alumno, access_token)
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    
    user, alumno, coach = test_athlete
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    
    # Set authorization header
    client.defaults['HTTP_AUTHORIZATION'] = f"Bearer {access_token}"
    
    return client, user, alumno, access_token
