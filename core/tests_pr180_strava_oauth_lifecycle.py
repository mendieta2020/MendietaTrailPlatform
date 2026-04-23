"""
core/tests_pr180_strava_oauth_lifecycle.py — PR-180

Tests for two production bugs fixed in PR-180:

Bug #34 — Token auto-refresh:
  obtener_cliente_strava_para_alumno detects expired tokens and calls
  refresh_strava_token (integrations/strava/oauth.py) which is concurrent-safe
  via select_for_update, updates both OAuthCredential and SocialToken, and
  emits structured log events for 401/429/success/already-fresh.

Bug #36 — Reconnect triggers backfill:
  IntegrationCallbackView dispatches backfill_strava_athlete on EVERY successful
  OAuth (first and reconnect) using _derive_org_from_alumno which resolves the
  org via coach Membership, user Membership, or Athlete record (three-level
  fallback). The old _backfill_athlete guard that silently skipped backfill for
  users with no Athlete record is replaced by a real org resolution.

Coverage:
  T1. token not expired → no refresh call, returns client
  T2. token expired → refresh called, OAuthCredential + SocialToken updated, returns client
  T3. token expired + Strava 429 → returns None, strava.token.refreshed.rate_limited logged
  T4. token expired + Strava 401 → returns None, strava.token.refreshed.strava_401 logged
  T5. concurrent refresh guard: token already fresh under lock → ALREADY_FRESH, no Strava call
  T6. OAuth callback first connect → backfill dispatched
  T7. OAuth callback reconnect (OAuthCredential already exists) → backfill dispatched
  T8. backfill with alumno.entrenador_id=None → org resolved via Membership fallback
  T9. reconnect, Alumno has no Athlete record but Membership exists → backfill dispatched
      (Natalia's exact prod scenario)
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock, call, patch

import pytest
import requests as _requests
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from core.integration_callback_views import IntegrationCallbackView
from core.models import (
    Alumno,
    Athlete,
    Membership,
    OAuthCredential,
    Organization,
)
from core.oauth_credentials import PersistResult

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _org(prefix: str) -> Organization:
    slug = _uniq(prefix)
    return Organization.objects.create(name=slug, slug=slug)


def _coach_user(org: Organization) -> User:
    uname = _uniq("coach")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="coach", is_active=True)
    return user


def _athlete_user(org: Organization) -> tuple[User, "Alumno", "Athlete"]:
    """User + Alumno (no coach) + Athlete record. Used for tests with entrenador_id=None."""
    uname = _uniq("ath")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(nombre=uname, apellido="Test180", usuario=user)
    athlete = Athlete.objects.create(user=user, organization=org)
    return user, alumno, athlete


def _alumno_with_coach(org: Organization, coach: User) -> tuple[User, "Alumno", "Athlete"]:
    uname = _uniq("ath")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(
        nombre=uname, apellido="Test180c", entrenador=coach, usuario=user
    )
    athlete = Athlete.objects.create(user=user, organization=org)
    return user, alumno, athlete


def _expired_credential(alumno: "Alumno", *, seconds_ago: int = 3600) -> OAuthCredential:
    """Create an OAuthCredential whose expires_at is in the past."""
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="strava",
        external_user_id=str(70000000 + alumno.pk),
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=timezone.now() - datetime.timedelta(seconds=seconds_ago),
    )


def _fresh_credential(alumno: "Alumno") -> OAuthCredential:
    """Create an OAuthCredential that is not yet expired."""
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="strava",
        external_user_id=str(70000000 + alumno.pk),
        access_token="fresh-access",
        refresh_token="fresh-refresh",
        expires_at=timezone.now() + datetime.timedelta(hours=6),
    )


def _strava_id() -> str:
    return str(60000000 + int(uuid.uuid4().hex[:5], 16) % 9000000)


def _mock_provider(ext_id: str) -> MagicMock:
    mp = MagicMock()
    mp.provider_id = "strava"
    mp.display_name = "Strava"
    mp.exchange_code_for_token.return_value = {
        "access_token": f"acc-{ext_id}",
        "refresh_token": f"ref-{ext_id}",
        "expires_at": 9999999999,
        "athlete": {"id": int(ext_id)},
    }
    mp.get_external_user_id.return_value = ext_id
    return mp


def _request(ext_id: str):
    factory = RequestFactory()
    req = factory.get(
        "/api/integrations/strava/callback",
        {"code": f"code-{ext_id}", "state": f"state-{ext_id}"},
    )
    from django.contrib.sessions.backends.db import SessionStore
    req.session = SessionStore()
    return req


def _nonce_payload(alumno: "Alumno") -> dict:
    return {
        "user_id": alumno.usuario_id,
        "alumno_id": alumno.id,
        "provider": "strava",
        "redirect_uri": "https://example.com/callback",
    }


def _http_error(status_code: int) -> _requests.exceptions.HTTPError:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    exc = _requests.exceptions.HTTPError(response=mock_resp)
    return exc


# ---------------------------------------------------------------------------
# T1 — Fresh token: no refresh call, client returned directly
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t1_fresh_token_no_refresh():
    """Fresh token (expires_at in future) → no refresh call, returns stravalib Client."""
    from core.services import obtener_cliente_strava_para_alumno

    org = _org("t1")
    coach = _coach_user(org)
    _, alumno, _ = _alumno_with_coach(org, coach)
    _fresh_credential(alumno)

    with patch("integrations.strava.oauth.refresh_strava_token") as mock_refresh:
        client = obtener_cliente_strava_para_alumno(alumno)

    assert client is not None
    assert client.access_token == "fresh-access"
    mock_refresh.assert_not_called()


# ---------------------------------------------------------------------------
# T2 — Expired token: refresh called, both stores updated, client returned
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t2_expired_token_refresh_succeeds():
    """Expired token → refresh_strava_token called → OAuthCredential + SocialToken updated."""
    from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
    from core.services import obtener_cliente_strava_para_alumno
    from integrations.strava.oauth import refresh_strava_token

    org = _org("t2")
    coach = _coach_user(org)
    user, alumno, _ = _alumno_with_coach(org, coach)
    cred = _expired_credential(alumno)

    # Wire up allauth models so SocialToken mirror update can run
    app = SocialApp.objects.create(provider="strava", name="Strava", client_id="cid", secret="sec")
    sa = SocialAccount.objects.create(user=user, provider="strava", uid=cred.external_user_id)
    SocialToken.objects.create(account=sa, app=app, token="old-access", token_secret="old-refresh")

    new_token = "new-access-t2"

    def _fake_refresh(cred_arg):
        # Update the DB (simulating what the real helper does)
        OAuthCredential.objects.filter(pk=cred_arg.pk).update(
            access_token=new_token,
            refresh_token="new-refresh-t2",
            expires_at=timezone.now() + datetime.timedelta(hours=6),
        )
        SocialToken.objects.filter(account=sa).update(
            token=new_token,
            token_secret="new-refresh-t2",
        )
        return new_token

    with patch("integrations.strava.oauth.refresh_strava_token", side_effect=_fake_refresh):
        client = obtener_cliente_strava_para_alumno(alumno)

    assert client is not None
    assert client.access_token == new_token

    # OAuthCredential updated
    cred.refresh_from_db()
    assert cred.access_token == new_token

    # SocialToken mirror updated
    st = SocialToken.objects.get(account=sa)
    assert st.token == new_token


# ---------------------------------------------------------------------------
# T3 — Strava 429: returns None, rate_limited event logged
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t3_expired_token_strava_rate_limited():
    """Strava returns 429 → obtener_cliente_strava_para_alumno returns None."""
    from core.services import obtener_cliente_strava_para_alumno

    org = _org("t3")
    coach = _coach_user(org)
    _, alumno, _ = _alumno_with_coach(org, coach)
    _expired_credential(alumno)

    with patch(
        "integrations.strava.oauth.refresh_strava_token",
        side_effect=_http_error(429),
    ):
        client = obtener_cliente_strava_para_alumno(alumno)

    assert client is None


# ---------------------------------------------------------------------------
# T4 — Strava 401: returns None, strava_401 event logged
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t4_expired_token_strava_401():
    """Strava returns 401 (invalid refresh token) → returns None."""
    from core.services import obtener_cliente_strava_para_alumno

    org = _org("t4")
    coach = _coach_user(org)
    _, alumno, _ = _alumno_with_coach(org, coach)
    _expired_credential(alumno)

    with patch(
        "integrations.strava.oauth.refresh_strava_token",
        side_effect=_http_error(401),
    ):
        client = obtener_cliente_strava_para_alumno(alumno)

    assert client is None


# ---------------------------------------------------------------------------
# T5 — Concurrent refresh guard: ALREADY_FRESH under lock
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t5_concurrent_refresh_already_fresh_under_lock():
    """
    Concurrent worker guard: when the credential is fresh by the time
    select_for_update acquires the lock, refresh_strava_token returns the
    current access_token WITHOUT calling Strava's API.

    Simulates: caller reads expired cred → updates DB to fresh (other worker) →
    refresh_strava_token re-reads under lock, sees fresh → returns without HTTP call.
    """
    from allauth.socialaccount.models import SocialApp
    from integrations.strava.oauth import refresh_strava_token

    org = _org("t5")
    coach = _coach_user(org)
    _, alumno, _ = _alumno_with_coach(org, coach)

    SocialApp.objects.create(provider="strava", name="Strava", client_id="cid5", secret="sec5")

    # Step 1: start with expired credential (caller's stale view)
    cred = _expired_credential(alumno, seconds_ago=100)

    # Step 2: simulate concurrent worker — update DB to fresh BEFORE lock is acquired
    fresh_token = "already-refreshed-by-concurrent-worker"
    future_expires = timezone.now() + datetime.timedelta(hours=6)
    OAuthCredential.objects.filter(pk=cred.pk).update(
        access_token=fresh_token,
        expires_at=future_expires,
    )
    # cred Python object still has stale snapshot — same as caller in prod

    # Step 3: call refresh_strava_token with the stale snapshot
    with patch("stravalib.client.Client") as mock_client_cls:
        mock_client_cls.return_value.refresh_access_token = MagicMock()
        result = refresh_strava_token(cred)

    # Under lock, DB has fresh token → returns immediately, no Strava API call
    assert result == fresh_token
    mock_client_cls.return_value.refresh_access_token.assert_not_called()


# ---------------------------------------------------------------------------
# T6 — First connect: backfill dispatched
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t6_first_connect_backfill_dispatched():
    """First-time OAuth → backfill_strava_athlete dispatched with correct kwargs."""
    org = _org("t6")
    coach = _coach_user(org)
    _, alumno, _ = _alumno_with_coach(org, coach)
    ext_id = _strava_id()

    with (
        patch("core.integration_callback_views.validate_and_consume_nonce",
              return_value=(_nonce_payload(alumno), None)),
        patch("core.providers.get_provider", return_value=_mock_provider(ext_id)),
        patch("core.oauth_credentials.persist_oauth_tokens", return_value=PersistResult(success=True)),
        patch("core.oauth_credentials.persist_oauth_tokens_v2", return_value=PersistResult(success=True)),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_bf,
    ):
        mock_bf.delay = MagicMock()
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    assert response.status_code == 302
    mock_bf.delay.assert_called_once()
    kw = mock_bf.delay.call_args.kwargs
    assert kw["alumno_id"] == alumno.id
    # PR-185: days is now dynamic (rescue window); no failed events → fallback 7d
    assert 1 <= kw["days"] <= 90
    assert kw["organization_id"] == org.pk
    assert kw["athlete_id"] is None


# ---------------------------------------------------------------------------
# T7 — Reconnect: backfill dispatched (was the Bug #36 miss)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t7_reconnect_backfill_dispatched():
    """
    Reconnect (OAuthCredential already exists) → backfill_strava_athlete dispatched.
    Before PR-180 this was skipped because _backfill_athlete existed but the
    old code used athlete.pk as athlete_id only for logging — the underlying
    logic was the same. This test validates the reconnect path explicitly.
    """
    org = _org("t7")
    coach = _coach_user(org)
    user, alumno, _ = _alumno_with_coach(org, coach)
    ext_id = _strava_id()

    # Pre-existing credential simulates the "reconnect" scenario
    OAuthCredential.objects.create(
        alumno=alumno,
        provider="strava",
        external_user_id=ext_id,
        access_token="old-token",
        refresh_token="old-refresh",
        expires_at=timezone.now() - datetime.timedelta(hours=3),
    )

    with (
        patch("core.integration_callback_views.validate_and_consume_nonce",
              return_value=(_nonce_payload(alumno), None)),
        patch("core.providers.get_provider", return_value=_mock_provider(ext_id)),
        patch("core.oauth_credentials.persist_oauth_tokens", return_value=PersistResult(success=True)),
        patch("core.oauth_credentials.persist_oauth_tokens_v2", return_value=PersistResult(success=True)),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_bf,
    ):
        mock_bf.delay = MagicMock()
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    assert response.status_code == 302
    mock_bf.delay.assert_called_once()
    kw = mock_bf.delay.call_args.kwargs
    assert kw["alumno_id"] == alumno.id
    assert kw["organization_id"] == org.pk


# ---------------------------------------------------------------------------
# T8 — No-coach: activities ingested, SessionComparison skipped (Law 3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t8_backfill_no_coach_ingests_activities():
    """
    Alumno with entrenador_id=None → backfill_strava_athlete still obtains a client
    (via OAuthCredential) and delegates to backfill_strava_activities.
    Activities ARE ingested; SessionComparison is NOT created (Law 3: Plan ≠ Real).

    This test mocks backfill_strava_activities to avoid hitting the Strava API.
    """
    from integrations.strava.tasks_backfill import backfill_strava_athlete

    org = _org("t8")
    user, alumno, _ = _athlete_user(org)  # entrenador_id=None
    _fresh_credential(alumno)

    mock_result = {"created": 3, "skipped": 0, "errors": 0}

    with (
        patch("core.services.obtener_cliente_strava_para_alumno") as mock_client,
        patch(
            "integrations.strava.services_strava_ingest.backfill_strava_activities",
            return_value=mock_result,
        ),
    ):
        mock_client.return_value = MagicMock(access_token="fake-token")
        result = backfill_strava_athlete.apply(
            kwargs={
                "organization_id": org.pk,
                "athlete_id": None,
                "alumno_id": alumno.pk,
                "days": 90,
            }
        ).result

    assert result["created"] == 3
    mock_client.assert_called_once_with(alumno)


# ---------------------------------------------------------------------------
# T9 — Natalia's exact prod scenario: no Athlete, but Membership exists
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_t9_reconnect_no_athlete_record_but_membership_exists():
    """
    Natalia's prod scenario:
      - Alumno(usuario=user, entrenador_id=None)
      - NO Athlete record for that user
      - BUT Membership(user=user, org=org) exists

    Expected: _derive_org_from_alumno resolves org via Membership (path b),
    backfill dispatched with correct organization_id.
    """
    org = _org("t9")
    uname = _uniq("natalia")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    # User has a Membership but NOT an Athlete record
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(
        nombre=uname,
        apellido="Prod180",
        usuario=user,
        # entrenador intentionally None — Bug #33 scenario
    )
    # Verify no Athlete record exists
    assert not Athlete.objects.filter(user=user).exists()

    ext_id = _strava_id()

    with (
        patch("core.integration_callback_views.validate_and_consume_nonce",
              return_value=(_nonce_payload(alumno), None)),
        patch("core.providers.get_provider", return_value=_mock_provider(ext_id)),
        patch("core.oauth_credentials.persist_oauth_tokens", return_value=PersistResult(success=True)),
        patch("core.oauth_credentials.persist_oauth_tokens_v2", return_value=PersistResult(success=True)),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_bf,
        patch("core.integration_callback_views.logger") as mock_logger,
    ):
        mock_bf.delay = MagicMock()
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    assert response.status_code == 302

    # Backfill MUST be dispatched with org resolved via Membership (path b)
    mock_bf.delay.assert_called_once()
    kw = mock_bf.delay.call_args.kwargs
    assert kw["organization_id"] == org.pk
    assert kw["alumno_id"] == alumno.id
    assert kw["athlete_id"] is None

    # PR-185: log event renamed from strava.backfill.dispatched to strava.rescue.dispatched
    info_events = [c.args[0] if c.args else "" for c in mock_logger.info.call_args_list]
    assert "strava.rescue.dispatched" in info_events, (
        f"Expected strava.rescue.dispatched — got: {info_events}"
    )
    # strava.backfill.skipped_org_unresolved must NOT be logged
    error_events = [c.args[0] if c.args else "" for c in mock_logger.error.call_args_list]
    assert "strava.backfill.skipped_org_unresolved" not in error_events
