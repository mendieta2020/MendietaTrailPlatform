"""
PR-135 — AthleteInvitation backend.

13 tests covering:
- InvitationCreateView: happy path, plan gate, cross-org plan
- InvitationDetailView: public access, expired detection
- InvitationAcceptView: happy path (creates AthleteSubscription), already accepted,
  expired, no coach MP credential
- InvitationRejectView: happy path, non-pending
- InvitationResendView: regenerates token, cross-org forbidden

All MP API calls are mocked — no real HTTP requests.
"""
import uuid
import pytest
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from core.models import (
    Athlete,
    AthleteInvitation,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    OrgOAuthCredential,
    Organization,
    OrganizationSubscription,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email=None):
    return User.objects.create_user(
        username=username,
        password="testpass",
        email=email or f"{username}@example.com",
    )


def _membership(user, org, role="coach"):
    return Membership.objects.create(user=user, organization=org, role=role)


def _pro_subscription(org):
    sub, _ = OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": "pro", "is_active": True},
    )
    return sub


def _free_subscription(org):
    past = timezone.now() - timedelta(days=1)
    OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": "free", "is_active": True, "trial_ends_at": past},
    )
    return Organization.objects.get(pk=org.pk)


def _plan(org, name="Plan Online", price="5000.00", mp_plan_id="mp_plan_test_001"):
    return CoachPricingPlan.objects.create(
        organization=org,
        name=name,
        price_ars=price,
        mp_plan_id=mp_plan_id,
    )


def _mp_credential(org):
    return OrgOAuthCredential.objects.create(
        organization=org,
        provider="mercadopago",
        access_token="coach_access_token_redacted",
        refresh_token="",
        provider_user_id="mp_user_123",
    )


def _invitation(org, plan, email="athlete@example.com", days=7):
    return AthleteInvitation.objects.create(
        organization=org,
        coach_plan=plan,
        email=email,
        expires_at=timezone.now() + timedelta(days=days),
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _authed_post(view_class, url_kwargs, data, user, org):
    """POST via APIRequestFactory with auth_organization set."""
    factory = APIRequestFactory()
    req = factory.post("/fake/", data=data, format="json")
    req.user = user
    req.auth_organization = org
    view = view_class.as_view()
    return view(req, **url_kwargs)


def _authed_get(view_class, url_kwargs, user, org):
    """GET via APIRequestFactory with auth_organization set."""
    factory = APIRequestFactory()
    req = factory.get("/fake/")
    req.user = user
    req.auth_organization = org
    view = view_class.as_view()
    return view(req, **url_kwargs)


# ---------------------------------------------------------------------------
# InvitationCreateView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_coach_can_create_invitation():
    """Owner creates invitation — returns token + invite_url (30-day expiry)."""
    from core.views_billing import InvitationCreateView

    org = _org("org-inv-1")
    user = _user("owner1")
    _membership(user, org, role="owner")
    _pro_subscription(org)
    plan = _plan(org)

    response = _authed_post(
        InvitationCreateView, {}, {"coach_plan": plan.pk, "email": "athlete@test.com"}, user, org
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert "token" in response.data
    assert "invite_url" in response.data
    assert AthleteInvitation.objects.filter(email="athlete@test.com", organization=org).exists()


@pytest.mark.django_db
def test_create_requires_pro_plan():
    """Free plan → 402 Payment Required."""
    from core.views_billing import InvitationCreateView

    org = _org("org-inv-2")
    user = _user("owner2")
    _membership(user, org, role="owner")
    free_org = _free_subscription(org)
    plan = _plan(free_org)

    response = _authed_post(
        InvitationCreateView, {}, {"coach_plan": plan.pk, "email": "athlete@test.com"}, user, free_org
    )
    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED


@pytest.mark.django_db
def test_create_validates_cross_org_plan():
    """Plan from another org → 400 validation error."""
    from core.views_billing import InvitationCreateView

    org_a = _org("org-inv-3a")
    org_b = _org("org-inv-3b")
    user = _user("owner3")
    _membership(user, org_a, role="owner")
    _pro_subscription(org_a)
    plan_b = _plan(org_b, name="Plan B")  # belongs to org_b

    response = _authed_post(
        InvitationCreateView, {}, {"coach_plan": plan_b.pk, "email": "x@test.com"}, user, org_a
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_coach_member_cannot_create_invitation():
    """Role=coach (empleado) cannot create invitations → 403."""
    from core.views_billing import InvitationCreateView

    org = _org("org-inv-4")
    user = _user("coach_member1")
    _membership(user, org, role="coach")
    _pro_subscription(org)
    plan = _plan(org, name="Plan Coach Member")

    response = _authed_post(
        InvitationCreateView, {}, {"coach_plan": plan.pk, "email": "athlete@test.com"}, user, org
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# InvitationDetailView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_invitation_detail_public():
    """Unauthenticated GET returns invitation details."""
    from core.views_billing import InvitationDetailView

    org = _org("org-det-1")
    plan = _plan(org)
    inv = _invitation(org, plan, email="detail@test.com")

    factory = APIRequestFactory()
    req = factory.get("/fake/")
    view = InvitationDetailView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == "detail@test.com"
    assert response.data["status"] == AthleteInvitation.Status.PENDING


@pytest.mark.django_db
def test_invitation_detail_expired():
    """Expired invitation → marks EXPIRED + returns 410."""
    from core.views_billing import InvitationDetailView

    org = _org("org-det-2")
    plan = _plan(org)
    inv = _invitation(org, plan, email="expired@test.com", days=-1)

    factory = APIRequestFactory()
    req = factory.get("/fake/")
    view = InvitationDetailView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_410_GONE
    inv.refresh_from_db()
    assert inv.status == AthleteInvitation.Status.EXPIRED


# ---------------------------------------------------------------------------
# InvitationAcceptView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_happy_path():
    """
    Authenticated athlete accepts → creates AthleteSubscription pending.
    MP call is mocked. Uses APIClient with force_authenticate so DRF
    correctly resolves request.user even with authentication_classes = [].
    """
    org = _org("org-acc-1")
    athlete_user = _user("athlete_acc1", email="acc1@test.com")
    _membership(athlete_user, org, role="athlete")
    athlete = _athlete(athlete_user, org)
    plan = _plan(org)
    _mp_credential(org)
    inv = _invitation(org, plan, email="acc1@test.com")

    with patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value={"id": "preapproval_abc123", "init_point": "https://mp.link"},
    ):
        client = APIClient()
        client.force_authenticate(user=athlete_user)
        resp = client.post(f"/api/billing/invitations/{inv.token}/accept/")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["status"] == "accepted"
    assert resp.data["mp_preapproval_id"] == "preapproval_abc123"
    inv.refresh_from_db()
    assert inv.status == AthleteInvitation.Status.ACCEPTED
    assert inv.mp_preapproval_id == "preapproval_abc123"
    assert AthleteSubscription.objects.filter(
        athlete=athlete, coach_plan=plan
    ).exists()


@pytest.mark.django_db
def test_accept_already_accepted():
    """Trying to accept a non-pending invitation → 400."""
    from core.views_billing import InvitationAcceptView

    org = _org("org-acc-2")
    plan = _plan(org)
    _mp_credential(org)
    inv = _invitation(org, plan)
    inv.status = AthleteInvitation.Status.ACCEPTED
    inv.save()

    factory = APIRequestFactory()
    req = factory.post("/fake/", {}, format="json")
    view = InvitationAcceptView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accept_expired():
    """Expired invitation → 410."""
    from core.views_billing import InvitationAcceptView

    org = _org("org-acc-3")
    plan = _plan(org)
    _mp_credential(org)
    inv = _invitation(org, plan, days=-1)

    factory = APIRequestFactory()
    req = factory.post("/fake/", {}, format="json")
    view = InvitationAcceptView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_410_GONE
    inv.refresh_from_db()
    assert inv.status == AthleteInvitation.Status.EXPIRED


@pytest.mark.django_db
def test_accept_no_coach_mp_credential():
    """Coach has no MP credential → 402."""
    from core.views_billing import InvitationAcceptView

    org = _org("org-acc-4")
    plan = _plan(org)
    # NO _mp_credential(org) call
    inv = _invitation(org, plan)

    factory = APIRequestFactory()
    req = factory.post("/fake/", {}, format="json")
    view = InvitationAcceptView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED


# ---------------------------------------------------------------------------
# InvitationRejectView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reject_happy_path():
    """Athlete rejects → status=rejected."""
    from core.views_billing import InvitationRejectView

    org = _org("org-rej-1")
    plan = _plan(org)
    inv = _invitation(org, plan)

    factory = APIRequestFactory()
    req = factory.post("/fake/", {}, format="json")
    view = InvitationRejectView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "rejected"
    inv.refresh_from_db()
    assert inv.status == AthleteInvitation.Status.REJECTED


@pytest.mark.django_db
def test_reject_non_pending():
    """Rejecting an already-rejected invitation → 400."""
    from core.views_billing import InvitationRejectView

    org = _org("org-rej-2")
    plan = _plan(org)
    inv = _invitation(org, plan)
    inv.status = AthleteInvitation.Status.REJECTED
    inv.save()

    factory = APIRequestFactory()
    req = factory.post("/fake/", {}, format="json")
    view = InvitationRejectView.as_view()
    response = view(req, token=inv.token)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# InvitationResendView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resend_regenerates_token():
    """Owner resends → new token, 30-day expiry, status=pending."""
    from core.views_billing import InvitationResendView

    org = _org("org-res-1")
    user = _user("owner_res1")
    _membership(user, org, role="owner")
    _pro_subscription(org)
    plan = _plan(org)
    inv = _invitation(org, plan)
    old_token = inv.token

    response = _authed_post(InvitationResendView, {"token": old_token}, {}, user, org)

    assert response.status_code == status.HTTP_200_OK
    new_token = uuid.UUID(response.data["token"])
    assert new_token != old_token
    assert "invite_url" in response.data
    inv.refresh_from_db()
    assert inv.token == new_token
    assert inv.status == AthleteInvitation.Status.PENDING
    assert inv.expires_at > timezone.now()


@pytest.mark.django_db
def test_resend_cross_org_forbidden():
    """Owner from another org cannot resend — cross-org isolation → 403."""
    from core.views_billing import InvitationResendView

    org_a = _org("org-res-2a")
    org_b = _org("org-res-2b")
    owner_b = _user("owner_res2b")
    _membership(owner_b, org_b, role="owner")
    _pro_subscription(org_b)
    plan_a = _plan(org_a, name="Plan A Resend")
    inv = _invitation(org_a, plan_a)

    # Owner from org_b tries to resend invitation belonging to org_a
    response = _authed_post(
        InvitationResendView, {"token": inv.token}, {}, owner_b, org_b
    )

    assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
