"""
PR-149 — Security Sweep: Tenancy Leak Fixes

Protective tests verifying:
  1. BillingOrgMixin.get_org() — deterministic resolution for multi-org users
  2. _get_athlete_membership() — deterministic resolution for multi-org athletes
  3. _get_coach_membership()  — deterministic resolution for multi-org coaches
  4. Legacy ViewSets (AlumnoViewSet, EquipoViewSet) — cross-coach isolation
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APIRequestFactory

from core.models import Alumno, Equipo, Membership, Organization
from core.views_billing import BillingOrgMixin, BillingStatusView
from core.views_pmc import _get_athlete_membership, _get_coach_membership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(name_suffix):
    org = Organization.objects.create(name=f"Org {name_suffix}", slug=f"org-{name_suffix}")
    return org


def _make_user(username):
    return User.objects.create_user(username=username, password="x")


def _make_membership(user, org, role="coach"):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _get_request(method="GET", user=None, query_params=None, data=None):
    """Build a minimal DRF request-like object via APIRequestFactory."""
    factory = APIRequestFactory()
    if method == "GET":
        req = factory.get("/api/billing/status/", query_params or {})
    else:
        req = factory.post("/api/billing/", data or {}, format="json")
    req.user = user
    return req


# ===========================================================================
# 1. BillingOrgMixin.get_org() — deterministic org resolution
# ===========================================================================

@pytest.mark.django_db
def test_billing_single_org_resolves_without_org_id():
    """Single-org coach gets their org without needing org_id param."""
    user = _make_user("b_single_coach")
    org = _make_org("b1")
    _make_membership(user, org, role="coach")

    req = _get_request(user=user)
    result = BillingOrgMixin().get_org(req)

    assert result == org


@pytest.mark.django_db
def test_billing_multi_org_returns_none_without_org_id():
    """
    Multi-org coach: get_org() must return None (→ 403) when org_id
    is not supplied — never silently pick one.
    """
    user = _make_user("b_multi_coach")
    org_a = _make_org("bmA")
    org_b = _make_org("bmB")
    _make_membership(user, org_a, role="coach")
    _make_membership(user, org_b, role="coach")

    req = _get_request(user=user)
    result = BillingOrgMixin().get_org(req)

    assert result is None, "Must not silently select one org for a multi-org user"


@pytest.mark.django_db
def test_billing_multi_org_with_org_id_selects_correct_org():
    """Multi-org coach + explicit org_id → returns the specified org."""
    user = _make_user("b_multi_coach2")
    org_a = _make_org("bmC")
    org_b = _make_org("bmD")
    _make_membership(user, org_a, role="coach")
    _make_membership(user, org_b, role="coach")

    req = _get_request(user=user, query_params={"org_id": str(org_b.pk)})
    result = BillingOrgMixin().get_org(req)

    assert result == org_b


@pytest.mark.django_db
def test_billing_multi_org_wrong_org_id_returns_none():
    """Multi-org coach with org_id of an org they don't belong to → None."""
    user = _make_user("b_multi_coach3")
    org_a = _make_org("bmE")
    other_org = _make_org("bmF")  # user is NOT a member
    _make_membership(user, org_a, role="coach")

    req = _get_request(user=user, query_params={"org_id": str(other_org.pk)})
    result = BillingOrgMixin().get_org(req)

    assert result is None


@pytest.mark.django_db
def test_billing_status_view_returns_403_for_multi_org_without_org_id():
    """End-to-end: BillingStatusView returns 403 for multi-org coach with no org_id."""
    user = _make_user("b_e2e_coach")
    org_a = _make_org("beA")
    org_b = _make_org("beB")
    _make_membership(user, org_a, role="coach")
    _make_membership(user, org_b, role="coach")

    factory = APIRequestFactory()
    req = factory.get("/api/billing/status/")
    req.user = user
    response = BillingStatusView.as_view()(req)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ===========================================================================
# 2. _get_athlete_membership() — deterministic resolution
# ===========================================================================

@pytest.mark.django_db
def test_pmc_athlete_single_org_resolves_without_org_id():
    """Single-org athlete: membership resolves without org_id param."""
    user = _make_user("pmc_athlete_single")
    org = _make_org("pA1")
    m = _make_membership(user, org, role="athlete")

    factory = APIRequestFactory()
    req = factory.get("/api/athlete/pmc/")
    req.user = user

    result = _get_athlete_membership(req)
    assert result == m


@pytest.mark.django_db
def test_pmc_athlete_multi_org_raises_validation_without_org_id():
    """
    Multi-org athlete without org_id → ValidationError, never silent selection.
    """
    user = _make_user("pmc_athlete_multi")
    org_a = _make_org("pA2")
    org_b = _make_org("pA3")
    _make_membership(user, org_a, role="athlete")
    _make_membership(user, org_b, role="athlete")

    factory = APIRequestFactory()
    req = factory.get("/api/athlete/pmc/")
    req.user = user

    with pytest.raises(ValidationError):
        _get_athlete_membership(req)


@pytest.mark.django_db
def test_pmc_athlete_multi_org_with_org_id_returns_correct_membership():
    """Multi-org athlete + org_id → resolves membership for the specified org."""
    user = _make_user("pmc_athlete_multi2")
    org_a = _make_org("pA4")
    org_b = _make_org("pA5")
    m_a = _make_membership(user, org_a, role="athlete")
    _make_membership(user, org_b, role="athlete")

    factory = APIRequestFactory()
    req = factory.get("/api/athlete/pmc/", {"org_id": str(org_a.pk)})
    req.user = user

    result = _get_athlete_membership(req)
    assert result == m_a


# ===========================================================================
# 3. _get_coach_membership() — deterministic resolution
# ===========================================================================

@pytest.mark.django_db
def test_pmc_coach_multi_org_raises_validation_without_org_id():
    """Multi-org coach without org_id → ValidationError."""
    user = _make_user("pmc_coach_multi")
    org_a = _make_org("pC1")
    org_b = _make_org("pC2")
    _make_membership(user, org_a, role="coach")
    _make_membership(user, org_b, role="coach")

    factory = APIRequestFactory()
    req = factory.get("/api/coach/team-readiness/")
    req.user = user

    with pytest.raises(ValidationError):
        _get_coach_membership(req)


@pytest.mark.django_db
def test_pmc_coach_multi_org_with_org_id_returns_correct_membership():
    """Multi-org coach + org_id → resolves membership for the specified org."""
    user = _make_user("pmc_coach_multi2")
    org_a = _make_org("pC3")
    org_b = _make_org("pC4")
    _make_membership(user, org_a, role="coach")
    m_b = _make_membership(user, org_b, role="coach")

    factory = APIRequestFactory()
    req = factory.get("/api/coach/team-readiness/", {"org_id": str(org_b.pk)})
    req.user = user

    result = _get_coach_membership(req)
    assert result == m_b


# ===========================================================================
# 4. Legacy ViewSets — cross-coach isolation (pre-Organization model)
# ===========================================================================

@pytest.mark.django_db
def test_alumno_viewset_coach_a_cannot_see_coach_b_athletes():
    """
    AlumnoViewSet: TenantModelViewSet scopes by entrenador=request.user.
    Coach A must not see Coach B's alumnos.
    """
    coach_a = _make_user("legacy_coach_a")
    coach_b = _make_user("legacy_coach_b")

    alumno_a = Alumno.objects.create(
        entrenador=coach_a, nombre="AthleteA", apellido="Test"
    )
    Alumno.objects.create(
        entrenador=coach_b, nombre="AthleteB", apellido="Test"
    )

    client = APIClient()
    client.force_authenticate(user=coach_a)
    response = client.get("/api/alumnos/")

    assert response.status_code == status.HTTP_200_OK
    # Coach A only sees their own athlete
    ids = [item["id"] for item in response.data.get("results", response.data)]
    assert alumno_a.pk in ids
    # Coach B's athlete must NOT appear
    assert all(
        item.get("entrenador") != coach_b.pk
        for item in response.data.get("results", response.data)
    ), "Coach A must not see Coach B's alumnos"


@pytest.mark.django_db
def test_equipo_viewset_coach_a_cannot_see_coach_b_teams():
    """
    EquipoViewSet: TenantModelViewSet scopes by entrenador=request.user.
    Coach A must not see Coach B's equipos.
    """
    coach_a = _make_user("legacy_equipo_coach_a")
    coach_b = _make_user("legacy_equipo_coach_b")

    equipo_a = Equipo.objects.create(nombre="Team A", entrenador=coach_a)
    Equipo.objects.create(nombre="Team B", entrenador=coach_b)

    client = APIClient()
    client.force_authenticate(user=coach_a)
    response = client.get("/api/equipos/")

    assert response.status_code == status.HTTP_200_OK
    ids = [item["id"] for item in response.data.get("results", response.data)]
    assert equipo_a.pk in ids
    assert all(
        item.get("entrenador") != coach_b.pk
        for item in response.data.get("results", response.data)
    ), "Coach A must not see Coach B's equipos"
