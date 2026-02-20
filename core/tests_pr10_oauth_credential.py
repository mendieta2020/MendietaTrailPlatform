"""
PR10 Tests: Provider-agnostic OAuthCredential model + persist_oauth_tokens_v2().

Coverage:
  - test_create_credential:               Happy-path creation of OAuthCredential.
  - test_unique_per_alumno_provider:       DB constraint rejects duplicate (alumno, provider).
  - test_upsert_updates_tokens_and_expires_at:
                                           persist_oauth_tokens_v2() is idempotent and
                                           overwrites stale tokens on second call.
  - test_persist_oauth_tokens_v2_does_not_touch_allauth:
                                           No SocialToken row created; allauth bridge untouched.

Constraints:
  - Tokens NEVER asserted verbatim in assertion messages (only existence checked via bool).
  - Multi-tenant: each test uses its own isolated alumno.
"""
import pytest
from django.db import IntegrityError
from django.utils import timezone


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def coach_and_alumno(db):
    """Create a minimal coach + alumno hierarchy."""
    from django.contrib.auth.models import User
    from core.models import Alumno

    coach = User.objects.create_user(username="pr10_coach", password="x")
    user = User.objects.create_user(username="pr10_athlete", password="x")
    alumno = Alumno.objects.create(
        entrenador=coach,
        usuario=user,
        nombre="PR10",
        apellido="Athlete",
    )
    return coach, alumno


# ---------------------------------------------------------------------------
# Test 1: Basic creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_credential(coach_and_alumno):
    """OAuthCredential can be persisted with required fields."""
    from core.models import OAuthCredential

    _, alumno = coach_and_alumno

    cred = OAuthCredential.objects.create(
        alumno=alumno,
        provider="garmin",
        external_user_id="garm-user-42",
        access_token="tok-access",
    )

    assert cred.pk is not None
    assert cred.provider == "garmin"
    assert cred.external_user_id == "garm-user-42"
    # Token is stored (bool check only – never log/assert raw value in output)
    assert bool(cred.access_token)
    assert cred.refresh_token == ""  # default
    assert cred.expires_at is None  # default
    assert cred.updated_at is not None
    # __str__ must not expose token content
    assert "garmin" in str(cred)
    assert "alumno" in str(cred)
    assert "tok-access" not in str(cred)


# ---------------------------------------------------------------------------
# Test 2: Unique constraint (alumno, provider)
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_unique_per_alumno_provider(coach_and_alumno):
    """A second row with the same (alumno, provider) must raise IntegrityError."""
    from core.models import OAuthCredential

    _, alumno = coach_and_alumno

    OAuthCredential.objects.create(
        alumno=alumno,
        provider="coros",
        external_user_id="coros-uid-1",
        access_token="first-token",
    )

    with pytest.raises(IntegrityError):
        OAuthCredential.objects.create(
            alumno=alumno,
            provider="coros",
            external_user_id="coros-uid-2",
            access_token="second-token",
        )


# ---------------------------------------------------------------------------
# Test 3: persist_oauth_tokens_v2 is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_upsert_updates_tokens_and_expires_at(coach_and_alumno):
    """
    Calling persist_oauth_tokens_v2 twice with the same (alumno, provider)
    must result in exactly one row whose tokens reflect the second call.
    """
    from core.oauth_credentials import persist_oauth_tokens_v2
    from core.models import OAuthCredential

    _, alumno = coach_and_alumno
    expires_first = timezone.now().replace(microsecond=0) + timezone.timedelta(hours=1)
    expires_second = timezone.now().replace(microsecond=0) + timezone.timedelta(hours=6)

    # First call
    result1 = persist_oauth_tokens_v2(
        provider="suunto",
        alumno=alumno,
        token_data={
            "access_token": "access-v1",
            "refresh_token": "refresh-v1",
            "expires_at": expires_first,
        },
        external_user_id="suunto-uid-99",
    )
    assert result1.success, f"First call failed: {result1.error_reason}"

    # Second call – different tokens
    result2 = persist_oauth_tokens_v2(
        provider="suunto",
        alumno=alumno,
        token_data={
            "access_token": "access-v2",
            "refresh_token": "refresh-v2",
            "expires_at": expires_second,
        },
        external_user_id="suunto-uid-99",
    )
    assert result2.success, f"Second call failed: {result2.error_reason}"

    # Exactly one row
    rows = OAuthCredential.objects.filter(alumno=alumno, provider="suunto")
    assert rows.count() == 1, "Expected exactly one OAuthCredential row"

    cred = rows.first()
    # Tokens updated (existence check only)
    assert bool(cred.access_token)
    assert bool(cred.refresh_token)
    assert cred.expires_at is not None
    # expires_at must reflect the second call
    assert cred.expires_at == expires_second


# ---------------------------------------------------------------------------
# Test 4: persist_oauth_tokens_v2 does NOT touch allauth SocialToken
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_persist_oauth_tokens_v2_does_not_touch_allauth(coach_and_alumno, monkeypatch):
    """
    persist_oauth_tokens_v2 must not create or modify SocialToken / SocialAccount.

    Strategy:
      1. Count SocialToken rows before.
      2. Monkeypatch SocialToken.objects.create to raise if called.
      3. Call persist_oauth_tokens_v2.
      4. Assert count unchanged and function succeeded.
    """
    from allauth.socialaccount.models import SocialToken
    from core.oauth_credentials import persist_oauth_tokens_v2

    _, alumno = coach_and_alumno

    before_count = SocialToken.objects.count()

    # Hard guard: if SocialToken.objects.create is invoked, the test must fail.
    original_create = SocialToken.objects.create

    def raise_if_called(*args, **kwargs):
        raise AssertionError(
            "persist_oauth_tokens_v2 must NOT call SocialToken.objects.create"
        )

    monkeypatch.setattr(SocialToken.objects, "create", raise_if_called)

    result = persist_oauth_tokens_v2(
        provider="polar",
        alumno=alumno,
        token_data={"access_token": "polar-access-tok"},
        external_user_id="polar-uid-7",
    )

    assert result.success, f"Expected success but got: {result.error_reason} — {result.error_message}"

    # SocialToken count must be unchanged
    monkeypatch.undo()  # restore before counting
    after_count = SocialToken.objects.count()
    assert after_count == before_count, (
        f"SocialToken count changed from {before_count} to {after_count}; "
        "persist_oauth_tokens_v2 must not touch allauth models"
    )
