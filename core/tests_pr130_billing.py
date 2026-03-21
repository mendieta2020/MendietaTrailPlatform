"""
PR-130 — Billing Foundation tests.

Covers:
  - OrganizationSubscription default plan
  - has_plan() ordering logic
  - Inactive subscription gate
  - require_plan() decorator: 402 / 200 responses
  - Cross-org isolation (each test is self-contained)
"""
import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from core.models import Organization, Membership, OrganizationSubscription
from core.billing import require_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_org_with_subscription(plan="free", is_active=True, username_suffix=""):
    suffix = username_suffix or plan
    user = User.objects.create_user(username=f"user_{suffix}_{id(plan)}", password="x")
    org = Organization.objects.create(name=f"Org {suffix}", slug=f"org-{suffix}-{id(plan)}")
    Membership.objects.create(user=user, organization=org, role="owner", is_active=True)
    # Signal auto-creates a subscription; use update_or_create to set desired plan.
    # Clear trial_ends_at so tests exercise pure plan-level access (not trial path).
    sub, _ = OrganizationSubscription.objects.update_or_create(
        organization=org,
        defaults={"plan": plan, "is_active": is_active, "trial_ends_at": None},
    )
    # Refresh org to clear any cached reverse-accessor set during signal
    org.refresh_from_db()
    return org, sub


# ---------------------------------------------------------------------------
# 1. Default plan
# ---------------------------------------------------------------------------

def test_default_plan_is_free():
    # Check model-level field default without touching the DB
    # (signal now auto-creates subscriptions with plan='pro' on org creation)
    sub = OrganizationSubscription()
    assert sub.plan == OrganizationSubscription.Plan.FREE


# ---------------------------------------------------------------------------
# 2–6. has_plan() ordering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_has_plan_free_allows_free():
    _, sub = make_org_with_subscription(plan="free", username_suffix="hpff")
    assert sub.has_plan("free") is True


@pytest.mark.django_db
def test_has_plan_free_blocks_starter():
    _, sub = make_org_with_subscription(plan="free", username_suffix="hpfbs")
    assert sub.has_plan("starter") is False


@pytest.mark.django_db
def test_has_plan_pro_allows_starter():
    _, sub = make_org_with_subscription(plan="pro", username_suffix="hppas")
    assert sub.has_plan("starter") is True


@pytest.mark.django_db
def test_has_plan_pro_allows_pro():
    _, sub = make_org_with_subscription(plan="pro", username_suffix="hppap")
    assert sub.has_plan("pro") is True


@pytest.mark.django_db
def test_has_plan_pro_blocks_enterprise():
    _, sub = make_org_with_subscription(plan="pro", username_suffix="hppbe")
    assert sub.has_plan("enterprise") is False


# ---------------------------------------------------------------------------
# 7. Inactive subscription blocks all
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_inactive_subscription_blocks_all():
    _, sub = make_org_with_subscription(plan="enterprise", is_active=False, username_suffix="inactive")
    assert sub.has_plan("free") is False
    assert sub.has_plan("enterprise") is False


# ---------------------------------------------------------------------------
# 8–9. require_plan() gate: 402 and 200
# ---------------------------------------------------------------------------

class _FakeView:
    """Minimal DRF-style view class for decorator testing."""

    @require_plan("starter")
    def get(self, request, *args, **kwargs):
        return Response({"ok": True}, status=status.HTTP_200_OK)


@pytest.mark.django_db
def test_gate_returns_402_when_plan_too_low():
    org, _sub = make_org_with_subscription(plan="free", username_suffix="gate402")
    factory = APIRequestFactory()
    request = factory.get("/fake/")
    # Attach org the same way the real auth middleware does
    request.auth_organization = org

    view = _FakeView()
    response = view.get(request)
    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert response.data["required_plan"] == "starter"
    assert response.data["current_plan"] == "free"


@pytest.mark.django_db
def test_gate_returns_200_when_plan_meets_requirement():
    org, _sub = make_org_with_subscription(plan="starter", username_suffix="gate200")
    factory = APIRequestFactory()
    request = factory.get("/fake/")
    request.auth_organization = org

    view = _FakeView()
    response = view.get(request)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["ok"] is True


# ---------------------------------------------------------------------------
# 10. Cross-org isolation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cross_org_isolation():
    org_a, sub_a = make_org_with_subscription(plan="pro", username_suffix="iso_a")
    org_b, sub_b = make_org_with_subscription(plan="free", username_suffix="iso_b")

    # Each sub references only its own org
    assert sub_a.organization_id == org_a.pk
    assert sub_b.organization_id == org_b.pk
    assert sub_a.organization_id != sub_b.organization_id

    # Plan gates are independent
    assert sub_a.has_plan("pro") is True
    assert sub_b.has_plan("pro") is False
