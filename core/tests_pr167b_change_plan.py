"""
PR-167b — Fix delete plan + Athlete change plan

Tests:
1. GET /api/billing/plans/ returns only active plans (soft-deleted excluded)
2. DELETE /api/billing/plans/<pk>/ soft-deletes and excludes from next GET
3. GET /api/athlete/available-plans/ returns active plans with is_current annotation
4. POST /api/athlete/change-plan/ in trial updates plan without touching MP
5. POST /api/athlete/change-plan/ with same plan returns 400
6. POST /api/athlete/change-plan/ with mp_preapproval_id returns 400 (MP active guard)
"""
import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def org_with_plans():
    """Org with owner + two active plans + one inactive plan."""
    from core.models import Organization, Membership, CoachPricingPlan

    owner = User.objects.create_user(username="owner167b", email="owner167b@test.com", password="pw")
    org = Organization.objects.create(name="Org167b", slug="org-167b")
    Membership.objects.create(user=owner, organization=org, role="owner", is_active=True)

    plan_a = CoachPricingPlan.objects.create(
        organization=org, name="Plan A", price_ars=5000, is_active=True,
    )
    plan_b = CoachPricingPlan.objects.create(
        organization=org, name="Plan B", price_ars=10000, is_active=True,
    )
    plan_inactive = CoachPricingPlan.objects.create(
        organization=org, name="Plan Inactivo", price_ars=999, is_active=False,
    )
    return org, owner, plan_a, plan_b, plan_inactive


@pytest.fixture
def athlete_in_trial(org_with_plans):
    """Athlete with AthleteSubscription on plan_a in trial (no mp_preapproval_id)."""
    from core.models import Membership, Athlete, AthleteSubscription

    org, owner, plan_a, plan_b, plan_inactive = org_with_plans
    athlete_user = User.objects.create_user(
        username="athlete167b", email="athlete167b@test.com", password="pw"
    )
    m = Membership.objects.create(
        user=athlete_user, organization=org, role="athlete", is_active=True
    )
    athlete = Athlete.objects.create(user=athlete_user, organization=org)
    sub = AthleteSubscription.objects.create(
        athlete=athlete,
        organization=org,
        coach_plan=plan_a,
        status=AthleteSubscription.Status.PENDING,
        trial_ends_at=timezone.now() + timedelta(days=5),
        mp_preapproval_id=None,
    )
    return athlete_user, sub, org, plan_a, plan_b, plan_inactive


# ─── Tests: Coach plan list filters ──────────────────────────────────────────

@pytest.mark.django_db
def test_plan_list_excludes_inactive(org_with_plans):
    """GET /api/billing/plans/ returns only is_active=True plans."""
    org, owner, plan_a, plan_b, plan_inactive = org_with_plans
    client = APIClient()
    client.force_authenticate(owner)

    resp = client.get('/api/billing/plans/')
    assert resp.status_code == 200
    ids = [p['id'] for p in resp.data]
    assert plan_a.pk in ids
    assert plan_b.pk in ids
    assert plan_inactive.pk not in ids


@pytest.mark.django_db
def test_delete_plan_persists_after_refresh(org_with_plans):
    """DELETE soft-deletes plan; subsequent GET does not return it."""
    org, owner, plan_a, plan_b, plan_inactive = org_with_plans
    client = APIClient()
    client.force_authenticate(owner)

    # Delete plan_b
    resp = client.delete(f'/api/billing/plans/{plan_b.pk}/')
    assert resp.status_code == 200
    assert resp.data['deactivated'] is True

    # plan_b should no longer appear in list
    resp2 = client.get('/api/billing/plans/')
    assert resp2.status_code == 200
    ids = [p['id'] for p in resp2.data]
    assert plan_b.pk not in ids
    assert plan_a.pk in ids


# ─── Tests: Athlete available plans ──────────────────────────────────────────

@pytest.mark.django_db
def test_available_plans_returns_active_only(athlete_in_trial):
    """GET /api/athlete/available-plans/ returns active plans with is_current."""
    athlete_user, sub, org, plan_a, plan_b, plan_inactive = athlete_in_trial
    client = APIClient()
    client.force_authenticate(athlete_user)

    resp = client.get('/api/athlete/available-plans/')
    assert resp.status_code == 200
    plans = resp.data['plans']
    ids = [p['id'] for p in plans]
    assert plan_a.pk in ids
    assert plan_b.pk in ids
    assert plan_inactive.pk not in ids

    # plan_a is current
    current = next(p for p in plans if p['id'] == plan_a.pk)
    assert current['is_current'] is True
    other = next(p for p in plans if p['id'] == plan_b.pk)
    assert other['is_current'] is False


# ─── Tests: Change plan ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_change_plan_trial_updates_plan(athlete_in_trial):
    """POST /api/athlete/change-plan/ in trial updates coach_plan without touching MP."""
    athlete_user, sub, org, plan_a, plan_b, plan_inactive = athlete_in_trial
    client = APIClient()
    client.force_authenticate(athlete_user)

    resp = client.post('/api/athlete/change-plan/', {'new_plan_id': plan_b.pk})
    assert resp.status_code == 200
    assert resp.data['status'] == 'changed'
    assert resp.data['new_plan']['id'] == plan_b.pk

    sub.refresh_from_db()
    assert sub.coach_plan_id == plan_b.pk
    assert sub.mp_preapproval_id is None  # MP not touched


@pytest.mark.django_db
def test_change_plan_same_plan_returns_400(athlete_in_trial):
    """POST /api/athlete/change-plan/ with current plan returns 400."""
    athlete_user, sub, org, plan_a, plan_b, plan_inactive = athlete_in_trial
    client = APIClient()
    client.force_authenticate(athlete_user)

    resp = client.post('/api/athlete/change-plan/', {'new_plan_id': plan_a.pk})
    assert resp.status_code == 400
    assert 'Ya estás' in resp.data['detail']


@pytest.mark.django_db
def test_change_plan_with_mp_preapproval_returns_400(athlete_in_trial):
    """POST /api/athlete/change-plan/ with active MP preapproval returns 400 (guard)."""
    athlete_user, sub, org, plan_a, plan_b, plan_inactive = athlete_in_trial
    # Simulate MP-active subscription
    sub.mp_preapproval_id = "mp_preapproval_abc"
    sub.save(update_fields=["mp_preapproval_id"])

    client = APIClient()
    client.force_authenticate(athlete_user)

    resp = client.post('/api/athlete/change-plan/', {'new_plan_id': plan_b.pk})
    assert resp.status_code == 400
    assert 'MercadoPago' in resp.data['detail']


@pytest.mark.django_db
def test_available_plans_excludes_inactive_from_list(athlete_in_trial):
    """Soft-deleted plans must not appear in available-plans after deletion."""
    athlete_user, sub, org, plan_a, plan_b, plan_inactive = athlete_in_trial

    # Soft-delete plan_b via DELETE endpoint using owner
    owner_user = User.objects.get(username="owner167b")
    owner_client = APIClient()
    owner_client.force_authenticate(owner_user)
    owner_client.delete(f'/api/billing/plans/{plan_b.pk}/')

    athlete_client = APIClient()
    athlete_client.force_authenticate(athlete_user)
    resp = athlete_client.get('/api/athlete/available-plans/')
    assert resp.status_code == 200
    ids = [p['id'] for p in resp.data['plans']]
    assert plan_b.pk not in ids
