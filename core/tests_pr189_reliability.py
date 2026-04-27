"""
core/tests_pr189_reliability.py — PR-189

Tests for Fix 1: Strava 3rd fallback (SocialAccount) + logger.warning on link_required.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_strava_event(*, owner_id: str, object_id: str = "111222") -> "StravaWebhookEvent":
    from core.models import StravaWebhookEvent
    uid = uuid.uuid4().hex
    return StravaWebhookEvent.objects.create(
        event_uid=uid,
        provider="strava",
        object_type="activity",
        aspect_type="create",
        owner_id=int(owner_id),
        object_id=int(object_id),
        status=StravaWebhookEvent.Status.QUEUED,
    )


def _make_alumno(user):
    from core.models import Alumno
    return Alumno.objects.create(
        nombre="Test189",
        apellido="Fallback",
        usuario=user,
    )


# ---------------------------------------------------------------------------
# Test 1: 3rd fallback resolves via SocialAccount → no DEFERRED return
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProcessStravaEventResolveViaSocialAccount:
    def test_resolves_via_socialaccount_fallback(self):
        """
        Setup: SocialAccount(provider='strava', uid='99999') → User → Alumno.
        No ExternalIdentity, no strava_athlete_id on Alumno.
        Trigger process_strava_event.
        Assert: does NOT return 'DEFERRED: link_required',
                ExternalIdentity upserted with status=LINKED,
                drain_strava_events_for_athlete.delay called once.
        """
        from allauth.socialaccount.models import SocialAccount
        from core.models import ExternalIdentity, StravaWebhookEvent
        from core.tasks import process_strava_event

        owner_id = "99999"
        user = User.objects.create_user(
            username=_uniq("sa_user"), password="x", email=f"{_uniq('sa')}@t.com"
        )
        alumno = _make_alumno(user)
        SocialAccount.objects.create(provider="strava", uid=owner_id, user=user)

        event = _make_strava_event(owner_id=owner_id)

        # Stub out the heavy strava I/O — we only want to reach the fallback.
        with (
            patch("core.services.obtener_cliente_strava_para_alumno", return_value=None),
            patch(
                "core.tasks.drain_strava_events_for_athlete.delay"
            ) as mock_drain,
        ):
            # process_strava_event returns "DEFERRED: missing_oauth" or similar
            # (not "DEFERRED: link_required") because alumno IS resolved.
            result = process_strava_event(event.id)

        assert result != "DEFERRED: link_required", (
            f"Expected fallback to resolve alumno, got: {result}"
        )
        mock_drain.assert_called_once_with(provider="strava", owner_id=int(owner_id))

        # ExternalIdentity must exist with LINKED status
        identity = ExternalIdentity.objects.filter(
            provider="strava", external_user_id=owner_id
        ).first()
        assert identity is not None
        assert identity.status == ExternalIdentity.Status.LINKED
        assert identity.alumno_id == alumno.pk


# ---------------------------------------------------------------------------
# Test 2: link_required path emits logger.warning
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProcessStravaEventLinkRequiredWarning:
    def test_link_required_emits_warning(self):
        """
        Setup: No SocialAccount, no ExternalIdentity, no Alumno for owner_id.
        Assert: returns 'DEFERRED: link_required',
                logger.warning called with event_name='strava.identity.link_required'.
        """
        from core.tasks import process_strava_event

        owner_id = "77777777"
        event = _make_strava_event(owner_id=owner_id)

        with patch("core.tasks.logger") as mock_logger:
            result = process_strava_event(event.id)

        assert result == "DEFERRED: link_required"

        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if call.args and call.args[0] == "strava.identity.link_required"
        ]
        assert len(warning_calls) >= 1, (
            "Expected logger.warning('strava.identity.link_required', ...) to be called"
        )
        extra = warning_calls[0].kwargs.get("extra", {})
        assert extra.get("event_name") == "strava.identity.link_required"
        assert extra.get("outcome") == "deferred"
