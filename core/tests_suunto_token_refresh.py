"""
PR-X3 — Suunto token refresh: protective tests.

Coverage:
  1. refresh_token() calls Suunto endpoint with correct grant_type=refresh_token params.
  2. refresh_token() normalizes expires_in → expires_at (same as exchange_code_for_token).
  3. refresh_token() preserves existing expires_at if already present in response.
  4. ensure_fresh_token() returns stored access_token unchanged when not expired.
  5. ensure_fresh_token() calls refresh_token() when token is expired, saves new tokens.
  6. ensure_fresh_token() calls refresh_token() when expiry is within buffer window (<5min).
  7. ensure_fresh_token() skips refresh and logs warning when refresh_token field is empty.
  8. ensure_fresh_token() handles missing expires_at (None) by attempting refresh.
  9. ensure_fresh_token() propagates HTTPError so Celery task can retry.
 10. ensure_fresh_token() keeps old refresh_token when response omits it (non-rotating).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch, call

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coach_and_alumno(suffix="tr"):
    from core.models import Alumno
    coach = User.objects.create_user(username=f"coach_tokenrefresh_{suffix}", password="x")
    alumno = Alumno.objects.create(
        entrenador=coach, nombre="Athlete", apellido=f"TokenRefresh{suffix}"
    )
    return coach, alumno


def _make_credential(alumno, *, access_token="old_access", refresh_token="old_refresh", expires_at=None):
    from core.models import OAuthCredential
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="suunto",
        external_user_id="suunto_user_test",
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def _mock_refresh_response(*, access_token="new_access", refresh_token="new_refresh", expires_in=3600):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# 1. refresh_token() — correct POST params
# ---------------------------------------------------------------------------

def test_refresh_token_posts_correct_params():
    """refresh_token() must POST grant_type=refresh_token with client credentials."""
    from integrations.suunto.oauth import refresh_token

    mock_resp = _mock_refresh_response()

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp) as mock_post:
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            refresh_token("my_refresh_token")

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    posted_data = kwargs.get("data") or mock_post.call_args[0][1]
    # Unpack positional or keyword
    call_kwargs = mock_post.call_args
    posted_data = call_kwargs[1].get("data") if call_kwargs[1] else call_kwargs[0][1]
    assert posted_data["grant_type"] == "refresh_token"
    assert posted_data["refresh_token"] == "my_refresh_token"
    assert posted_data["client_id"] == "cid"
    assert posted_data["client_secret"] == "csec"
    assert "code" not in posted_data, "refresh flow must not send 'code'"


# ---------------------------------------------------------------------------
# 2. refresh_token() — expires_in normalization
# ---------------------------------------------------------------------------

def test_refresh_token_normalizes_expires_in():
    """refresh_token() must convert expires_in (seconds) → expires_at (unix ts)."""
    from integrations.suunto.oauth import refresh_token

    mock_resp = _mock_refresh_response(expires_in=3600)

    before = int(time.time())
    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            token_data = refresh_token("rt")
    after = int(time.time())

    assert "expires_at" in token_data
    assert before + 3600 <= token_data["expires_at"] <= after + 3600


# ---------------------------------------------------------------------------
# 3. refresh_token() — preserves existing expires_at
# ---------------------------------------------------------------------------

def test_refresh_token_preserves_existing_expires_at():
    """refresh_token() must not overwrite expires_at if already present in response."""
    from integrations.suunto.oauth import refresh_token

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_at",
        "refresh_token": "new_rt",
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": 9_999_999_999,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            token_data = refresh_token("rt")

    assert token_data["expires_at"] == 9_999_999_999, "Pre-existing expires_at must not be overwritten"


# ---------------------------------------------------------------------------
# 4. ensure_fresh_token() — token not expired → no HTTP call
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_skips_when_not_expired():
    """ensure_fresh_token() must return stored access_token when token has > 5min remaining."""
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("4")
    future = datetime.now(tz=dt_timezone.utc) + timedelta(hours=2)
    credential = _make_credential(alumno, access_token="valid_token", expires_at=future)

    with patch("integrations.suunto.oauth.http_requests.post") as mock_post:
        result = ensure_fresh_token(credential)

    mock_post.assert_not_called()
    assert result == "valid_token"


# ---------------------------------------------------------------------------
# 5. ensure_fresh_token() — expired token → refresh + save
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_expired_token():
    """ensure_fresh_token() must call Suunto API and persist new tokens when expired."""
    from core.models import OAuthCredential
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("5")
    past = datetime.now(tz=dt_timezone.utc) - timedelta(hours=1)
    credential = _make_credential(alumno, access_token="old_token", expires_at=past)

    mock_resp = _mock_refresh_response(access_token="fresh_access", refresh_token="fresh_refresh", expires_in=3600)

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            result = ensure_fresh_token(credential)

    assert result == "fresh_access"

    # Verify persisted to DB
    refreshed = OAuthCredential.objects.get(pk=credential.pk)
    assert refreshed.access_token == "fresh_access"
    assert refreshed.refresh_token == "fresh_refresh"
    assert refreshed.expires_at is not None
    assert refreshed.expires_at > datetime.now(tz=dt_timezone.utc)


# ---------------------------------------------------------------------------
# 6. ensure_fresh_token() — token within buffer window → refresh
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_when_nearly_expired():
    """ensure_fresh_token() must refresh when < 5 minutes remain (buffer window)."""
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("6")
    # 3 minutes in the future — inside the 5-minute buffer
    nearly_expired = datetime.now(tz=dt_timezone.utc) + timedelta(minutes=3)
    credential = _make_credential(alumno, access_token="almost_stale", expires_at=nearly_expired)

    mock_resp = _mock_refresh_response(access_token="renewed_access", expires_in=3600)

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            result = ensure_fresh_token(credential)

    assert result == "renewed_access"


# ---------------------------------------------------------------------------
# 7. ensure_fresh_token() — no refresh_token → log warning, return old token
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_skips_when_no_refresh_token(caplog):
    """ensure_fresh_token() must log a warning and return existing token when refresh_token is empty."""
    import logging
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("7")
    past = datetime.now(tz=dt_timezone.utc) - timedelta(hours=1)
    credential = _make_credential(alumno, access_token="stale_token", refresh_token="", expires_at=past)

    with patch("integrations.suunto.oauth.http_requests.post") as mock_post:
        with caplog.at_level(logging.WARNING, logger="integrations.suunto.oauth"):
            result = ensure_fresh_token(credential)

    mock_post.assert_not_called()
    assert result == "stale_token"
    assert any("no_refresh_token" in r.getMessage() or "no_refresh_token" in str(r.msg) for r in caplog.records)


# ---------------------------------------------------------------------------
# 8. ensure_fresh_token() — expires_at is None → attempt refresh
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_when_expires_at_is_none():
    """ensure_fresh_token() must treat missing expires_at as expired and attempt refresh."""
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("8")
    credential = _make_credential(alumno, access_token="no_expiry_token", expires_at=None)

    mock_resp = _mock_refresh_response(access_token="after_refresh_token", expires_in=3600)

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            result = ensure_fresh_token(credential)

    assert result == "after_refresh_token"


# ---------------------------------------------------------------------------
# 9. ensure_fresh_token() — HTTP error propagates (Celery retry)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_propagates_http_error():
    """ensure_fresh_token() must raise HTTPError so the Celery task can retry."""
    import requests as req_lib
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("9")
    past = datetime.now(tz=dt_timezone.utc) - timedelta(hours=1)
    credential = _make_credential(alumno, expires_at=past)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized")

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            with pytest.raises(req_lib.HTTPError):
                ensure_fresh_token(credential)


# ---------------------------------------------------------------------------
# 10. ensure_fresh_token() — response omits refresh_token → keep old one
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ensure_fresh_token_keeps_old_refresh_token_when_not_rotated():
    """ensure_fresh_token() must preserve the stored refresh_token if response omits it."""
    from core.models import OAuthCredential
    from integrations.suunto.oauth import ensure_fresh_token

    _, alumno = _make_coach_and_alumno("10")
    past = datetime.now(tz=dt_timezone.utc) - timedelta(hours=1)
    credential = _make_credential(
        alumno, access_token="old_at", refresh_token="keep_me", expires_at=past
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_at_no_rt",
        "token_type": "bearer",
        "expires_in": 3600,
        # refresh_token intentionally absent
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("integrations.suunto.oauth.http_requests.post", return_value=mock_resp):
        with patch("integrations.suunto.oauth.settings") as mock_settings:
            mock_settings.SUUNTO_CLIENT_ID = "cid"
            mock_settings.SUUNTO_CLIENT_SECRET = "csec"
            result = ensure_fresh_token(credential)

    assert result == "new_at_no_rt"
    refreshed = OAuthCredential.objects.get(pk=credential.pk)
    assert refreshed.refresh_token == "keep_me", "Old refresh_token must be preserved when response omits it"
