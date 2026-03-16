"""
Protective tests for PR-134: Suunto OAuth integration (Phase 1).

Coverage:
1. SuuntoProvider.enabled is True and provider is registered.
2. ExternalIdentity.Provider includes SUUNTO choice.
3. integrations/suunto/oauth.py: expires_in → expires_at normalization.
4. integrations/suunto/oauth.py: get_external_user_id extracts 'user' field.
5. IntegrationStartView returns authorization_url for suunto (config present).
6. IntegrationStartView returns 500 when SUUNTO_CLIENT_ID is missing.
7. IntegrationDisconnectView accepts suunto provider (no longer 400).
8. IntegrationDisconnectView still works correctly for strava (backward compat).
9. IntegrationDisconnectView returns 400 for unknown provider (law stays closed).
10. Law 4: SuuntoProvider methods use lazy imports, no module-level integrations import.
"""
import time
import ast
import textwrap
from pathlib import Path
from unittest.mock import patch, Mock

import pytest
from django.contrib.auth.models import User

from core.models import Alumno, ExternalIdentity
from core.integration_models import OAuthIntegrationStatus
from core.oauth_state import generate_oauth_state
from core.providers import get_provider


# ---------------------------------------------------------------------------
# 1. Provider registry + enabled flag
# ---------------------------------------------------------------------------

def test_suunto_provider_is_registered():
    """SuuntoProvider must be returned by get_provider('suunto')."""
    provider = get_provider("suunto")
    assert provider is not None
    assert provider.provider_id == "suunto"


def test_suunto_provider_is_enabled():
    """SuuntoProvider.enabled must be True (PR-134 unblocks it)."""
    provider = get_provider("suunto")
    assert provider.enabled is True


# ---------------------------------------------------------------------------
# 2. ExternalIdentity model — SUUNTO choice
# ---------------------------------------------------------------------------

def test_externalidentity_provider_has_suunto():
    """ExternalIdentity.Provider TextChoices must include 'suunto'."""
    values = [v for v, _ in ExternalIdentity.Provider.choices]
    assert "suunto" in values, f"SUUNTO missing from ExternalIdentity.Provider; got: {values}"


# ---------------------------------------------------------------------------
# 3. Token normalization: expires_in → expires_at
# ---------------------------------------------------------------------------

def test_suunto_oauth_normalizes_expires_in_to_expires_at():
    """
    Suunto returns expires_in (seconds). The oauth module must convert it to
    expires_at (unix timestamp) so the domain callback layer treats all providers uniformly.
    """
    from integrations.suunto.oauth import exchange_code_for_token

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "suunto_access_abc",
        "refresh_token": "suunto_refresh_xyz",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": "suunto_athlete_username",
    }
    mock_response.raise_for_status = Mock()

    before = int(time.time())
    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_response):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "test_client_id"
            mock_settings.SUUNTO_CLIENT_SECRET = "test_client_secret"
            token_data = exchange_code_for_token("auth_code_123", "http://localhost/callback")
    after = int(time.time())

    assert "expires_at" in token_data, "expires_at must be present after normalization"
    assert before + 3600 <= token_data["expires_at"] <= after + 3600, (
        f"expires_at={token_data['expires_at']} is outside expected range "
        f"[{before + 3600}, {after + 3600}]"
    )


def test_suunto_oauth_preserves_existing_expires_at():
    """If token response already includes expires_at, do not overwrite it."""
    from integrations.suunto.oauth import exchange_code_for_token

    expected_expires_at = 9999999999  # Far future
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "suunto_access_abc",
        "refresh_token": "suunto_refresh_xyz",
        "expires_in": 3600,
        "expires_at": expected_expires_at,
        "user": "athlete",
    }
    mock_response.raise_for_status = Mock()

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_response):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csecret"
            token_data = exchange_code_for_token("code", "http://localhost/callback")

    assert token_data["expires_at"] == expected_expires_at


# ---------------------------------------------------------------------------
# 4. get_external_user_id extracts 'user' field
# ---------------------------------------------------------------------------

def test_suunto_get_external_user_id_extracts_user_field():
    from integrations.suunto.oauth import get_external_user_id

    token_data = {"access_token": "abc", "user": "suunto_username_42"}
    result = get_external_user_id(token_data)
    assert result == "suunto_username_42"


def test_suunto_get_external_user_id_raises_on_missing_user():
    from integrations.suunto.oauth import get_external_user_id

    with pytest.raises(ValueError, match="Missing 'user' field"):
        get_external_user_id({"access_token": "abc"})


# ---------------------------------------------------------------------------
# 5. IntegrationStartView — suunto with config present
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_integration_start_suunto_returns_authorization_url(client):
    """
    GIVEN: Authenticated athlete, SUUNTO_CLIENT_ID configured
    WHEN: POST /api/integrations/suunto/start
    THEN: 200 response with authorization_url pointing to Suunto's OAuth server
    """
    user = User.objects.create_user(username="athlete_suunto", password="testpass")
    coach = User.objects.create_user(username="coach_suunto", password="testpass")
    Alumno.objects.create(
        usuario=user,
        entrenador=coach,
        nombre="Suunto",
        apellido="Athlete",
    )
    client.force_login(user)

    with patch("core.integration_views.settings") as mock_settings:
        mock_settings.SUUNTO_CLIENT_ID = "test_suunto_client_id"
        mock_settings.PUBLIC_BASE_URL = "http://localhost:8000"
        # generate_oauth_state reads from cache — patch the whole start method path
        with patch("core.integration_views.generate_oauth_state", return_value="test_state_token"):
            with patch("core.providers.suunto.SuuntoProvider.get_oauth_authorize_url",
                       return_value="https://cloudapi-oauth.suunto.com/oauth/authorize?client_id=test_suunto_client_id&state=test_state_token"):
                response = client.post("/api/integrations/suunto/start")

    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "suunto" in data["authorization_url"]
    assert data["provider"] == "suunto"


# ---------------------------------------------------------------------------
# 6. IntegrationStartView — suunto without config returns 500
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_integration_start_suunto_missing_config_returns_500(client):
    """
    GIVEN: SUUNTO_CLIENT_ID is empty/missing
    WHEN: POST /api/integrations/suunto/start
    THEN: 500 server_misconfigured (not a client error)
    """
    user = User.objects.create_user(username="athlete_suunto2", password="testpass")
    coach = User.objects.create_user(username="coach_suunto2", password="testpass")
    Alumno.objects.create(
        usuario=user,
        entrenador=coach,
        nombre="Suunto",
        apellido="Athlete2",
    )
    client.force_login(user)

    with patch("core.integration_views.settings") as mock_settings:
        mock_settings.SUUNTO_CLIENT_ID = ""   # missing
        mock_settings.PUBLIC_BASE_URL = "http://localhost:8000"
        response = client.post("/api/integrations/suunto/start")

    assert response.status_code == 500
    assert response.json()["error"] == "provider_not_configured"


# ---------------------------------------------------------------------------
# 7. IntegrationDisconnectView — suunto no longer blocked
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_disconnect_suunto_returns_204_when_already_disconnected(client):
    """
    GIVEN: Authenticated athlete with no Suunto credentials stored
    WHEN: DELETE /api/integrations/suunto/disconnect/
    THEN: 204 No Content (idempotent — not a 400 "unsupported" any more)
    """
    user = User.objects.create_user(username="athlete_disc_suunto", password="testpass")
    coach = User.objects.create_user(username="coach_disc_suunto", password="testpass")
    Alumno.objects.create(
        usuario=user,
        entrenador=coach,
        nombre="Suunto",
        apellido="Disc",
    )
    client.force_login(user)

    response = client.delete("/api/integrations/suunto/disconnect/")

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# 8. IntegrationDisconnectView — strava backward compat (Law 2)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_disconnect_strava_still_returns_204(client):
    """
    Strava disconnect must still work after the generic refactor (Law 2).
    No credentials stored → idempotent 204.
    """
    user = User.objects.create_user(username="athlete_disc_strava", password="testpass")
    coach = User.objects.create_user(username="coach_disc_strava", password="testpass")
    Alumno.objects.create(
        usuario=user,
        entrenador=coach,
        nombre="Strava",
        apellido="Disc",
    )
    client.force_login(user)

    response = client.delete("/api/integrations/strava/disconnect/")

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# 9. IntegrationDisconnectView — unknown provider → 400 (fail-closed)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_disconnect_unknown_provider_returns_400(client):
    """
    Unknown provider must still return 400 (fail-closed — do not allow
    arbitrary provider strings to execute disconnect logic).
    """
    user = User.objects.create_user(username="athlete_disc_unknown", password="testpass")
    client.force_login(user)

    response = client.delete("/api/integrations/notaprovider/disconnect/")

    assert response.status_code == 400
    assert response.json()["error"] == "unknown_provider"


# ---------------------------------------------------------------------------
# 10. Law 4: SuuntoProvider uses lazy imports (no module-level integrations import)
# ---------------------------------------------------------------------------

def test_suunto_provider_module_has_no_toplevel_integrations_import():
    """
    core/providers/suunto.py must NOT have module-level imports from integrations/.
    Provider methods must use lazy (function-level) imports (Law 4).
    """
    provider_path = Path(__file__).parent / "providers" / "suunto.py"
    source = provider_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Top-level imports are direct children of the Module node
    top_level_imports = [
        node for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    for node in top_level_imports:
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("integrations"), (
                f"Law 4 violation: core/providers/suunto.py has a module-level import "
                f"from '{node.module}' at line {node.lineno}. "
                f"Use a lazy import inside the method body instead."
            )
