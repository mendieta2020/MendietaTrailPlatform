"""
core/tests_pr175_custom_oauth_backfill.py — PR-175

Tests: backfill_strava_athlete dispatched from the custom integration
OAuth callback (IntegrationCallbackView), not just from the allauth
signal handler.

Root cause addressed: IntegrationCallbackView routes through
/api/integrations/<provider>/callback — it bypasses allauth entirely so
social_account_added / social_account_updated never fire. Before PR-175,
backfill_strava_athlete.delay() was never called for athletes who
connected via this path.

Coverage:
  1. test_backfill_dispatched_on_successful_custom_callback
       Full custom callback success path → backfill_strava_athlete.delay
       called with correct kwargs (organization_id, athlete_id, alumno_id,
       days=90).
  2. test_backfill_dispatch_logged
       Same success path → oauth.callback.backfill_task_dispatched info
       log emitted with correct extra fields.
  3. test_backfill_failure_is_non_blocking
       backfill_strava_athlete.delay raises (simulating Celery/Redis down)
       → logger.exception called, callback still returns 302 success to
       athlete.
  4. test_drain_still_dispatched_on_success
       Regression: drain_strava_events_for_athlete.delay still fires after
       PR-175 changes.
  5. test_flow_identified_log_emitted
       oauth.callback.flow_identified logged with flow="custom_integration".

Patch targets note:
  get_provider, persist_oauth_tokens, persist_oauth_tokens_v2 and
  backfill_strava_athlete are all local imports inside the view method
  body. They must be patched at their source modules so the local import
  picks up the mock at call time.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from core.integration_callback_views import IntegrationCallbackView
from core.models import (
    Alumno,
    Athlete,
    Membership,
    Organization,
)
from core.oauth_credentials import PersistResult

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
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


def _athlete_setup(org: Organization, coach: User) -> tuple[User, Alumno, Athlete]:
    """Create athlete user + Alumno + new-style Athlete. Returns (user, alumno, athlete)."""
    uname = _uniq("ath")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(
        nombre=uname,
        apellido="Test175",
        entrenador=coach,
        usuario=user,
    )
    athlete = Athlete.objects.create(user=user, organization=org)
    return user, alumno, athlete


def _strava_id() -> str:
    return str(60000000 + int(uuid.uuid4().hex[:5], 16) % 9000000)


def _athlete_setup_no_athlete_record(org: Organization, coach: User) -> tuple[User, Alumno]:
    """Create athlete user + Alumno but NO Athlete record (race condition scenario)."""
    uname = _uniq("ath-norecord")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(
        nombre=uname,
        apellido="NoRecord175",
        entrenador=coach,
        usuario=user,
    )
    return user, alumno


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


def _request(ext_id: str) -> object:
    factory = RequestFactory()
    req = factory.get(
        "/api/integrations/strava/callback",
        {"code": f"code-{ext_id}", "state": f"state-{ext_id}"},
    )
    from django.contrib.sessions.backends.db import SessionStore
    req.session = SessionStore()
    return req


def _nonce_payload(alumno: Alumno) -> dict:
    return {
        "user_id": alumno.usuario_id,
        "alumno_id": alumno.id,
        "provider": "strava",
        "redirect_uri": "https://example.com/callback",
    }


# ---------------------------------------------------------------------------
# Test 1 — backfill.delay called with correct kwargs on success
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_dispatched_on_successful_custom_callback():
    """
    Custom integration OAuth success → backfill_strava_athlete.delay called
    with organization_id, athlete_id, alumno_id, days=90.
    """
    org = _org("org-175-t1")
    coach = _coach_user(org)
    _, alumno, athlete = _athlete_setup(org, coach)
    ext_id = _strava_id()

    mock_drain = MagicMock()
    mock_drain.delay = MagicMock()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.integration_callback_views.drain_strava_events_for_athlete",
            mock_drain,
        ),
        patch(
            "integrations.strava.tasks_backfill.backfill_strava_athlete",
        ) as mock_bf,
    ):
        mock_bf.delay = MagicMock()
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    assert response.status_code == 302
    mock_bf.delay.assert_called_once()
    kwargs = mock_bf.delay.call_args.kwargs
    assert kwargs["alumno_id"] == alumno.id
    # PR-185: days is now dynamic (rescue window). No failed events in test DB →
    # fallback 7d. Assert 1 <= days <= 90 to tolerate sub-day clock rounding.
    assert 1 <= kwargs["days"] <= 90
    assert kwargs["organization_id"] == athlete.organization_id
    assert kwargs["athlete_id"] is None  # PR-180: athlete_id is logging-only, passed as None


# ---------------------------------------------------------------------------
# Test 2 — backfill dispatch info log emitted
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_dispatch_logged():
    """
    oauth.callback.backfill_task_dispatched info log emitted on success
    with correct extra fields.
    """
    org = _org("org-175-t2")
    coach = _coach_user(org)
    _, alumno, athlete = _athlete_setup(org, coach)
    ext_id = _strava_id()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete"),
        patch("core.integration_callback_views.logger") as mock_logger,
    ):
        IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    info_events = [
        (c.args[0] if c.args else "", c.kwargs.get("extra", {}))
        for c in mock_logger.info.call_args_list
    ]
    event_names = [name for name, _ in info_events]
    # PR-185: log event renamed from strava.backfill.dispatched to strava.rescue.dispatched
    assert "strava.rescue.dispatched" in event_names, (
        f"Expected strava.rescue.dispatched; got: {event_names}"
    )

    _, extra = next(e for e in info_events if e[0] == "strava.rescue.dispatched")
    assert extra.get("alumno_id") == alumno.id
    # PR-185: days is dynamic (rescue window); no failed events → fallback 7d
    assert 1 <= extra.get("days") <= 90


# ---------------------------------------------------------------------------
# Test 3 — backfill failure is non-blocking (logger.exception + 302 still)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_failure_is_non_blocking():
    """
    If backfill_strava_athlete.delay raises (Redis down / Celery unavailable),
    logger.exception is called and the OAuth callback still returns 302 success.
    """
    org = _org("org-175-t3")
    coach = _coach_user(org)
    _, alumno, _ = _athlete_setup(org, coach)
    ext_id = _strava_id()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch(
            "integrations.strava.tasks_backfill.backfill_strava_athlete",
        ) as mock_bf,
        patch("core.integration_callback_views.logger") as mock_logger,
    ):
        mock_bf.delay = MagicMock(side_effect=ConnectionError("Redis unavailable"))
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    # OAuth flow must still succeed despite backfill failure
    assert response.status_code == 302
    location = response.get("Location", "")
    assert "status=error" not in location

    exception_events = [c.args[0] if c.args else "" for c in mock_logger.exception.call_args_list]
    assert "oauth.callback.backfill_task_failed" in exception_events, (
        f"Expected oauth.callback.backfill_task_failed; got: {exception_events}"
    )


# ---------------------------------------------------------------------------
# Test 4 — drain still dispatched (regression)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_drain_still_dispatched_on_success():
    """
    Regression: drain_strava_events_for_athlete.delay must still be called
    after PR-175 changes. Adding backfill must not have broken drain.
    """
    org = _org("org-175-t4")
    coach = _coach_user(org)
    _, alumno, _ = _athlete_setup(org, coach)
    ext_id = _strava_id()

    mock_drain = MagicMock()
    mock_drain.delay = MagicMock()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.integration_callback_views.drain_strava_events_for_athlete",
            mock_drain,
        ),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete"),
    ):
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    assert response.status_code == 302
    mock_drain.delay.assert_called_once_with(
        provider="strava",
        owner_id=int(ext_id),
    )


# ---------------------------------------------------------------------------
# Test 5 — flow_identified log emitted
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_flow_identified_log_emitted():
    """
    oauth.callback.flow_identified must be logged with flow="custom_integration"
    on every successful custom callback.
    """
    org = _org("org-175-t5")
    coach = _coach_user(org)
    _, alumno, _ = _athlete_setup(org, coach)
    ext_id = _strava_id()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete"),
        patch("core.integration_callback_views.logger") as mock_logger,
    ):
        IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    info_events = [
        (c.args[0] if c.args else "", c.kwargs.get("extra", {}))
        for c in mock_logger.info.call_args_list
    ]
    event_names = [name for name, _ in info_events]
    assert "oauth.callback.flow_identified" in event_names, (
        f"Expected oauth.callback.flow_identified; got: {event_names}"
    )

    _, extra = next(e for e in info_events if e[0] == "oauth.callback.flow_identified")
    assert extra.get("flow") == "custom_integration"
    assert extra.get("alumno_id") == alumno.id


# ---------------------------------------------------------------------------
# Test 6 — no Athlete record → no dispatch, warning logged (guard fix)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_dispatched_when_athlete_record_missing_but_coach_exists():
    """
    PR-180: When no Athlete record exists but a coach Membership is present,
    _derive_org_from_alumno resolves the org via path (a) and backfill IS dispatched.

    This validates the fix for Natalia's prod scenario: reconnect with missing
    P1 Athlete record no longer silently skips the backfill.
    """
    org = _org("org-175-t6")
    coach = _coach_user(org)
    # Alumno exists, has a coach, but NO Athlete record (missing P1 migration).
    _, alumno = _athlete_setup_no_athlete_record(org, coach)
    ext_id = _strava_id()

    with (
        patch(
            "core.integration_callback_views.validate_and_consume_nonce",
            return_value=(_nonce_payload(alumno), None),
        ),
        patch(
            "core.providers.get_provider",
            return_value=_mock_provider(ext_id),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens",
            return_value=PersistResult(success=True),
        ),
        patch(
            "core.oauth_credentials.persist_oauth_tokens_v2",
            return_value=PersistResult(success=True),
        ),
        patch("core.integration_callback_views.drain_strava_events_for_athlete"),
        patch(
            "integrations.strava.tasks_backfill.backfill_strava_athlete",
        ) as mock_bf,
        patch("core.integration_callback_views.logger") as mock_logger,
    ):
        mock_bf.delay = MagicMock()
        response = IntegrationCallbackView.as_view()(_request(ext_id), provider="strava")

    # Callback must still succeed
    assert response.status_code == 302
    location = response.get("Location", "")
    assert "status=error" not in location

    # Backfill MUST be dispatched via coach org (path a)
    mock_bf.delay.assert_called_once()
    kwargs = mock_bf.delay.call_args.kwargs
    assert kwargs["alumno_id"] == alumno.id
    assert kwargs["organization_id"] == org.pk
    assert kwargs["athlete_id"] is None

    # PR-185: log event renamed from strava.backfill.dispatched to strava.rescue.dispatched
    info_events = [c.args[0] if c.args else "" for c in mock_logger.info.call_args_list]
    assert "strava.rescue.dispatched" in info_events, (
        f"Expected strava.rescue.dispatched; got: {info_events}"
    )
