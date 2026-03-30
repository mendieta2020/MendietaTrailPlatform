"""
PR-137 — Billing UI role guards.

Tests that coach (non-owner/admin) members receive 403 on the four new
billing endpoints introduced in PR-137:

    GET  /billing/plans/
    POST /billing/plans/
    GET  /billing/athlete-subscriptions/
    POST /billing/athlete-subscriptions/<id>/activate/
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from core.models import (
    Athlete,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    Organization,
    OrganizationSubscription,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (mirror pattern from tests_pr135_athlete_invitation.py)
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="testpass",
                                    email=f"{username}@example.com")


def _membership(user, org, role="coach"):
    return Membership.objects.create(user=user, organization=org, role=role)


def _pro_subscription(org):
    sub, _ = OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": "pro", "is_active": True},
    )
    return sub


def _plan(org, name="Plan Test"):
    return CoachPricingPlan.objects.create(
        organization=org, name=name, price_ars="5000.00"
    )


def _athlete_subscription(org, plan):
    user = User.objects.create_user(
        username=f"athlete_{org.slug}", password="x",
        email=f"athlete_{org.slug}@example.com",
    )
    athlete = Athlete.objects.create(user=user, organization=org)
    return AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status="pending",
    )


def _get(view_class, url_kwargs, user, org):
    factory = APIRequestFactory()
    req = factory.get("/fake/")
    req.user = user
    req.auth_organization = org
    return view_class.as_view()(req, **url_kwargs)


def _post(view_class, url_kwargs, data, user, org):
    factory = APIRequestFactory()
    req = factory.post("/fake/", data=data, format="json")
    req.user = user
    req.auth_organization = org
    return view_class.as_view()(req, **url_kwargs)


# ---------------------------------------------------------------------------
# GET /billing/plans/ — coach → 403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_pricing_plans_coach_allowed():
    """PR-150: Coach can list pricing plans (BillingOrgMixin includes coach role)."""
    from core.views_billing import CoachPricingPlanListCreateView

    org = _org("org-rg-plans-get")
    user = _user("coach_plans_get")
    _membership(user, org, role="coach")
    _pro_subscription(org)

    resp = _get(CoachPricingPlanListCreateView, {}, user, org)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /billing/plans/ — coach → allowed (PR-150)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_pricing_plans_coach_allowed():
    """PR-150: Coach can create pricing plans (BillingOrgMixin includes coach role)."""
    from core.views_billing import CoachPricingPlanListCreateView

    org = _org("org-rg-plans-post")
    user = _user("coach_plans_post")
    _membership(user, org, role="coach")
    _pro_subscription(org)

    resp = _post(CoachPricingPlanListCreateView, {},
                 {"name": "Coach Plan", "price_ars": "999.00"}, user, org)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# GET /billing/athlete-subscriptions/ — coach → 403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_athlete_subscriptions_coach_403():
    """Coach member cannot list athlete subscriptions — must be owner/admin."""
    from core.views_billing import AthleteSubscriptionListView

    org = _org("org-rg-subs-get")
    user = _user("coach_subs_get")
    _membership(user, org, role="coach")
    _pro_subscription(org)

    resp = _get(AthleteSubscriptionListView, {}, user, org)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /billing/athlete-subscriptions/<id>/activate/ — coach → 403
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activate_subscription_coach_403():
    """Coach member cannot manually activate a subscription — must be owner/admin."""
    from core.views_billing import AthleteSubscriptionActivateView

    org = _org("org-rg-activate")
    user = _user("coach_activate")
    _membership(user, org, role="coach")
    _pro_subscription(org)
    plan = _plan(org)
    sub = _athlete_subscription(org, plan)

    resp = _post(AthleteSubscriptionActivateView, {"pk": sub.pk}, {}, user, org)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Sanity: owner CAN access these endpoints (not 403)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_pricing_plans_owner_200():
    """Owner can list pricing plans."""
    from core.views_billing import CoachPricingPlanListCreateView

    org = _org("org-rg-plans-owner")
    user = _user("owner_plans")
    _membership(user, org, role="owner")
    _pro_subscription(org)

    resp = _get(CoachPricingPlanListCreateView, {}, user, org)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_get_athlete_subscriptions_owner_200():
    """Owner can list athlete subscriptions."""
    from core.views_billing import AthleteSubscriptionListView

    org = _org("org-rg-subs-owner")
    user = _user("owner_subs")
    _membership(user, org, role="owner")
    _pro_subscription(org)

    resp = _get(AthleteSubscriptionListView, {}, user, org)
    assert resp.status_code == 200
