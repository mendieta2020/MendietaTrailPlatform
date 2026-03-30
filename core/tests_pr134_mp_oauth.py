"""
PR-134 — Coach MP OAuth Connect / Callback / Disconnect.

10 tests covering:
- MPConnectView: happy path, plan gate, unauthenticated
- MPCallbackView: happy path, idempotent update, bad code, missing state
- MPDisconnectView: happy path, plan gate
- Cross-org isolation

All external MP API calls are mocked — no real HTTP requests.
"""
import pytest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
from rest_framework.test import APIRequestFactory

from core.models import Membership, OrgOAuthCredential, Organization, OrganizationSubscription
from core.views_billing import MPCallbackView, MPConnectView, MPDisconnectView

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role="coach"):
    return Membership.objects.create(user=user, organization=org, role=role)


def _pro_subscription(org):
    """Ensure org has a pro subscription (signal may have auto-created a free one)."""
    sub, _ = OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": "pro", "is_active": True},
    )
    return sub


def _free_subscription(org):
    """
    Force org subscription to free/expired-trial and return a FRESH org instance.

    The post_save signal auto-creates a 15-day Pro trial. Django caches the
    reverse OneToOne on the org Python object, so callers must use the
    returned fresh_org (not the original org) when the plan gate needs to fire.
    """
    from django.utils import timezone
    from datetime import timedelta

    # Set trial_ends_at in the past so the trial gate does not promote free → pro.
    past = timezone.now() - timedelta(days=1)
    OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": "free", "is_active": True, "trial_ends_at": past},
    )
    # Return a fresh instance — the original org may have a cached subscription.
    return Organization.objects.get(pk=org.pk)


def _authenticated_get(url, user, org):
    factory = APIRequestFactory()
    req = factory.get(url)
    req.user = user
    req.auth_organization = org
    return req


def _authenticated_delete(url, user, org):
    factory = APIRequestFactory()
    req = factory.delete(url)
    req.user = user
    req.auth_organization = org
    return req


# ---------------------------------------------------------------------------
# MPConnectView — GET /api/billing/mp/connect/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_connect_returns_authorization_url():
    """Pro-plan org gets a valid MP authorization URL."""
    org = _org("org-134-c1")
    user = _user("coach-134-c1")
    _membership(user, org)
    _pro_subscription(org)

    req = _authenticated_get("/api/billing/mp/connect/", user, org)

    with patch(
        "integrations.mercadopago.oauth.mp_get_authorization_url",
        return_value="https://auth.mercadopago.com/authorization?client_id=TEST&state=1",
    ) as mock_url:
        response = MPConnectView.as_view()(req)

    assert response.status_code == status.HTTP_200_OK
    assert "authorization_url" in response.data
    assert response.data["authorization_url"].startswith("https://auth.mercadopago.com")
    mock_url.assert_called_once_with(org.pk)


@pytest.mark.django_db
def test_connect_available_for_any_plan():
    """PR-150: MP connect no longer requires pro plan — available to all authenticated owners."""
    org = _org("org-134-c2")
    user = _user("coach-134-c2")
    _membership(user, org)
    _free_subscription(org)

    req = _authenticated_get("/api/billing/mp/connect/", user, org)
    response = MPConnectView.as_view()(req)

    # Should return authorization URL, not 402
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_connect_requires_auth():
    """Anonymous request is rejected with 401."""
    factory = APIRequestFactory()
    req = factory.get("/api/billing/mp/connect/")
    req.user = AnonymousUser()

    response = MPConnectView.as_view()(req)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# MPCallbackView — GET /api/billing/mp/callback/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_callback_creates_oauth_credential():
    """Happy path: callback stores a new OrgOAuthCredential for the org."""
    org = _org("org-134-cb1")
    user = _user("coach-134-cb1")
    _membership(user, org)

    mock_token_data = {
        "access_token": "tok_abc",
        "refresh_token": "ref_abc",
        "user_id": 99001,
    }

    factory = APIRequestFactory()
    req = factory.get(
        "/api/billing/mp/callback/",
        {"code": "auth_code_123", "state": str(org.pk)},
    )
    req.user = AnonymousUser()

    with patch(
        "integrations.mercadopago.oauth.mp_exchange_code",
        return_value=mock_token_data,
    ):
        response = MPCallbackView.as_view()(req)

    assert response.status_code == 302  # redirect to frontend

    cred = OrgOAuthCredential.objects.get(organization=org, provider="mercadopago")
    assert cred.provider_user_id == "99001"
    # Tokens are stored — we only assert the record exists and user_id is correct.


@pytest.mark.django_db
def test_callback_updates_existing_credential():
    """Idempotency: calling callback twice updates the credential, does not duplicate."""
    org = _org("org-134-cb2")
    user = _user("coach-134-cb2")
    _membership(user, org)

    # Pre-existing credential
    OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="old_tok",
        refresh_token="old_ref",
        provider_user_id="88001",
    )

    new_token_data = {
        "access_token": "new_tok",
        "refresh_token": "new_ref",
        "user_id": 88002,
    }

    factory = APIRequestFactory()
    req = factory.get(
        "/api/billing/mp/callback/",
        {"code": "new_code", "state": str(org.pk)},
    )
    req.user = AnonymousUser()

    with patch(
        "integrations.mercadopago.oauth.mp_exchange_code",
        return_value=new_token_data,
    ):
        response = MPCallbackView.as_view()(req)

    assert response.status_code == 302

    # Still only one credential row
    assert OrgOAuthCredential.objects.filter(organization=org, provider="mercadopago").count() == 1
    cred = OrgOAuthCredential.objects.get(organization=org, provider="mercadopago")
    assert cred.provider_user_id == "88002"


@pytest.mark.django_db
def test_callback_bad_code_returns_400():
    """When mp_exchange_code raises ValueError, the callback returns 400."""
    org = _org("org-134-cb3")
    user = _user("coach-134-cb3")
    _membership(user, org)

    factory = APIRequestFactory()
    req = factory.get(
        "/api/billing/mp/callback/",
        {"code": "bad_code", "state": str(org.pk)},
    )
    req.user = AnonymousUser()

    with patch(
        "integrations.mercadopago.oauth.mp_exchange_code",
        side_effect=ValueError("MP token exchange failed with status 400"),
    ):
        response = MPCallbackView.as_view()(req)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_callback_missing_state_returns_400():
    """Callback without state param returns 400."""
    factory = APIRequestFactory()
    req = factory.get("/api/billing/mp/callback/", {"code": "some_code"})
    req.user = AnonymousUser()

    response = MPCallbackView.as_view()(req)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# MPDisconnectView — DELETE /api/billing/mp/disconnect/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_disconnect_removes_credential():
    """Pro-plan coach can disconnect their MP credential."""
    org = _org("org-134-d1")
    user = _user("coach-134-d1")
    _membership(user, org)
    _pro_subscription(org)

    OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="tok",
        provider_user_id="77001",
    )

    req = _authenticated_delete("/api/billing/mp/disconnect/", user, org)
    response = MPDisconnectView.as_view()(req)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"disconnected": True}
    assert not OrgOAuthCredential.objects.filter(organization=org, provider="mercadopago").exists()


@pytest.mark.django_db
def test_disconnect_requires_pro_plan():
    """Free-plan org is blocked with 402 when trying to disconnect."""
    org = _org("org-134-d2")
    user = _user("coach-134-d2")
    _membership(user, org)
    fresh_org = _free_subscription(org)  # returns fresh org without cached subscription

    req = _authenticated_delete("/api/billing/mp/disconnect/", user, fresh_org)
    response = MPDisconnectView.as_view()(req)

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cross_org_isolation():
    """
    Org A's MP credential is invisible to org B's filtered queryset.
    This validates Law 1: every query is organization-scoped.
    """
    org_a = _org("org-134-iso-a")
    org_b = _org("org-134-iso-b")

    OrgOAuthCredential.objects.create(
        organization=org_a,
        provider="mercadopago",
        access_token="tok_a",
        provider_user_id="66001",
    )

    # Org B has no credential — queryset must return empty
    qs_b = OrgOAuthCredential.objects.filter(organization=org_b, provider="mercadopago")
    assert qs_b.count() == 0

    # Org A queryset must return exactly one row
    qs_a = OrgOAuthCredential.objects.filter(organization=org_a, provider="mercadopago")
    assert qs_a.count() == 1
    assert qs_a.first().provider_user_id == "66001"
