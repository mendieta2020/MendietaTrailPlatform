"""
PR-133 — CoachPricingPlan + AthleteSubscription models.

10 tests covering:
- Model creation and field correctness
- __str__ representations
- UniqueConstraint (name×org, athlete×plan)
- PROTECT FK on plan deletion
- Cross-org isolation
"""
import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError

from core.models import (
    Athlete,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    Organization,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _plan(org, name="Plan Online", price="5000.00"):
    return CoachPricingPlan.objects.create(
        organization=org,
        name=name,
        price_ars=price,
    )


# ---------------------------------------------------------------------------
# CoachPricingPlan tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_coach_pricing_plan_saves_correctly():
    org = _org("org-t1")
    plan = _plan(org, name="Programa Presencial", price="8000.00")

    assert plan.pk is not None
    assert plan.name == "Programa Presencial"
    assert str(plan.price_ars) == "8000.00"
    assert plan.organization == org
    assert plan.is_active is True
    assert plan.mp_plan_id is None


@pytest.mark.django_db
def test_coach_pricing_plan_str():
    org = _org("org-t2")
    plan = _plan(org, name="Online Elite", price="12000.50")

    result = str(plan)
    assert str(org) in result
    assert "Online Elite" in result
    assert "12000.50" in result


@pytest.mark.django_db
def test_coach_can_have_multiple_plans():
    org = _org("org-t3")
    p1 = _plan(org, name="Plan A", price="3000.00")
    p2 = _plan(org, name="Plan B", price="6000.00")

    assert CoachPricingPlan.objects.filter(organization=org).count() == 2
    assert p1.pk != p2.pk


@pytest.mark.django_db(transaction=True)
def test_plan_name_unique_per_org_raises_error():
    org = _org("org-t4")
    _plan(org, name="Duplicado")

    with pytest.raises(IntegrityError):
        _plan(org, name="Duplicado")


@pytest.mark.django_db
def test_same_plan_name_allowed_across_orgs():
    org_a = _org("org-t5a")
    org_b = _org("org-t5b")

    plan_a = _plan(org_a, name="Shared Name")
    plan_b = _plan(org_b, name="Shared Name")

    assert plan_a.pk != plan_b.pk


# ---------------------------------------------------------------------------
# AthleteSubscription tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_athlete_subscription_default_status_pending():
    org = _org("org-t6")
    user = _user("athlete-t6")
    athlete = _athlete(user, org)
    plan = _plan(org)

    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
    )

    assert sub.status == AthleteSubscription.Status.PENDING
    assert sub.mp_preapproval_id is None
    assert sub.last_payment_at is None
    assert sub.next_payment_at is None


@pytest.mark.django_db
def test_athlete_subscription_str():
    org = _org("org-t7")
    user = _user("athlete-t7")
    athlete = _athlete(user, org)
    plan = _plan(org, name="Plan STR")

    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
        status=AthleteSubscription.Status.ACTIVE,
    )

    result = str(sub)
    assert "Plan STR" in result
    assert "active" in result


@pytest.mark.django_db(transaction=True)
def test_unique_athlete_per_coach_plan_raises_error():
    org = _org("org-t8")
    user = _user("athlete-t8")
    athlete = _athlete(user, org)
    plan = _plan(org)

    AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
    )

    with pytest.raises(IntegrityError):
        AthleteSubscription.objects.create(
            athlete=athlete,
            organization=org,
            coach_plan=plan,
        )


@pytest.mark.django_db
def test_delete_coach_plan_with_subscription_raises_protected_error():
    org = _org("org-t9")
    user = _user("athlete-t9")
    athlete = _athlete(user, org)
    plan = _plan(org)

    AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan,
    )

    with pytest.raises(ProtectedError):
        plan.delete()


@pytest.mark.django_db
def test_athlete_subscription_org_isolation():
    org_a = _org("org-t10a")
    org_b = _org("org-t10b")

    user_a = _user("athlete-t10a")
    user_b = _user("athlete-t10b")

    athlete_a = _athlete(user_a, org_a)
    athlete_b = _athlete(user_b, org_b)

    plan_a = _plan(org_a, name="Plan A10")
    plan_b = _plan(org_b, name="Plan B10")

    sub_a = AthleteSubscription.objects.create(
        athlete=athlete_a,
        organization=org_a,
        coach_plan=plan_a,
    )
    AthleteSubscription.objects.create(
        athlete=athlete_b,
        organization=org_b,
        coach_plan=plan_b,
    )

    qs_a = AthleteSubscription.objects.filter(organization=org_a)
    assert qs_a.count() == 1
    assert qs_a.first().pk == sub_a.pk

    qs_b = AthleteSubscription.objects.filter(organization=org_b)
    assert qs_b.count() == 1
    assert qs_b.first().organization == org_b
