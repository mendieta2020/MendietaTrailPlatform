"""
PR-132 — Billing Views: Checkout Flow + Status
10 tests covering BillingStatusView, BillingSubscribeView, BillingCancelView.
"""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework import status

from core.models import Organization, Membership, OrganizationSubscription, SubscriptionPlan
from core.views_billing import BillingStatusView, BillingSubscribeView, BillingCancelView

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_org_with_coach(username="coach_user"):
    user = User.objects.create_user(username=username, email=f"{username}@test.com", password="x")
    org = Organization.objects.create(name=f"Org {username}")
    Membership.objects.create(user=user, organization=org, role="coach")
    return org, user


def make_subscription(org, plan="free", mp_preapproval_id=None, is_active=True):
    # The auto_create_subscription_with_trial signal fires on Organization.post_save,
    # so the subscription may already exist. Use update_or_create to avoid UniqueViolation.
    sub, _ = OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={
            "plan": plan,
            "is_active": is_active,
            "mp_preapproval_id": mp_preapproval_id,
        },
    )
    return sub


def make_plan(name="Pro", plan_tier="pro", mp_plan_id="mp_plan_abc", is_active=True):
    return SubscriptionPlan.objects.create(
        name=name,
        plan_tier=plan_tier,
        price_ars=1000,
        seats_included=10,
        mp_plan_id=mp_plan_id,
        is_active=is_active,
    )


def authenticated_request(method, user, org, data=None):
    factory = APIRequestFactory()
    if method == "GET":
        req = factory.get("/api/billing/status/")
    elif method == "POST":
        req = factory.post("/api/billing/", data or {}, format="json")
    else:
        raise ValueError(f"Unknown method: {method}")
    req.user = user
    req.auth_organization = org
    return req


# ---------------------------------------------------------------------------
# BillingStatusView tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_status_returns_plan_and_trial_info():
    org, user = make_org_with_coach("u_status_1")
    make_subscription(org, plan="starter")
    req = authenticated_request("GET", user, org)
    view = BillingStatusView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["plan"] == "starter"
    assert "is_in_trial" in response.data
    assert "trial_days_remaining" in response.data


@pytest.mark.django_db
def test_status_returns_seats_used():
    from core.models import Athlete, Coach
    org, user = make_org_with_coach("u_status_2")
    make_subscription(org, plan="pro")
    # Create a coach record so we can link athletes
    coach = Coach.objects.create(user=user, organization=org)
    Athlete.objects.create(user=user, organization=org, coach=coach, is_active=True)
    req = authenticated_request("GET", user, org)
    view = BillingStatusView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["seats_used"] == 1


@pytest.mark.django_db
def test_status_unauthenticated_returns_401():
    from django.contrib.auth.models import AnonymousUser
    factory = APIRequestFactory()
    req = factory.get("/api/billing/status/")
    req.user = AnonymousUser()
    req.auth_organization = None
    view = BillingStatusView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_status_no_subscription_returns_404():
    org, user = make_org_with_coach("u_status_4")
    # The signal auto-creates a subscription; delete it to test the 404 path.
    OrganizationSubscription.objects.filter(organization=org).delete()
    req = authenticated_request("GET", user, org)
    view = BillingStatusView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# BillingSubscribeView tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_subscribe_returns_checkout_url():
    org, user = make_org_with_coach("u_sub_1")
    plan = make_plan()
    mp_response = {"id": "preaprob_123", "init_point": "https://mp.com/checkout/123"}

    req = authenticated_request("POST", user, org, {"plan_id": plan.pk})
    view = BillingSubscribeView.as_view()

    with patch(
        "integrations.mercadopago.subscriptions.create_subscription",
        return_value=mp_response,
    ):
        response = view(req)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["checkout_url"] == "https://mp.com/checkout/123"
    assert response.data["mp_preapproval_id"] == "preaprob_123"
    assert response.data["plan"] == "pro"


@pytest.mark.django_db
def test_subscribe_invalid_plan_id_returns_404():
    org, user = make_org_with_coach("u_sub_2")
    req = authenticated_request("POST", user, org, {"plan_id": 99999})
    view = BillingSubscribeView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_subscribe_plan_without_mp_id_returns_400():
    org, user = make_org_with_coach("u_sub_3")
    plan = make_plan(mp_plan_id=None)
    plan.mp_plan_id = None
    plan.save()
    req = authenticated_request("POST", user, org, {"plan_id": plan.pk})
    view = BillingSubscribeView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "MercadoPago" in response.data["detail"]


@pytest.mark.django_db
def test_subscribe_mp_error_returns_502():
    org, user = make_org_with_coach("u_sub_4")
    plan = make_plan()

    req = authenticated_request("POST", user, org, {"plan_id": plan.pk})
    view = BillingSubscribeView.as_view()

    with patch(
        "integrations.mercadopago.subscriptions.create_subscription",
        side_effect=Exception("MP timeout"),
    ):
        response = view(req)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


# ---------------------------------------------------------------------------
# BillingCancelView tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_sets_plan_to_free():
    org, user = make_org_with_coach("u_cancel_1")
    sub = make_subscription(org, plan="pro", mp_preapproval_id="preaprob_abc")

    req = authenticated_request("POST", user, org)
    view = BillingCancelView.as_view()

    with patch(
        "integrations.mercadopago.subscriptions.cancel_subscription",
        return_value=None,
    ):
        response = view(req)

    assert response.status_code == status.HTTP_200_OK
    sub.refresh_from_db()
    assert sub.plan == OrganizationSubscription.Plan.FREE
    assert sub.is_active is False


@pytest.mark.django_db
def test_cancel_no_preapproval_id_returns_400():
    org, user = make_org_with_coach("u_cancel_2")
    make_subscription(org, plan="pro", mp_preapproval_id=None)

    req = authenticated_request("POST", user, org)
    view = BillingCancelView.as_view()
    response = view(req)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
