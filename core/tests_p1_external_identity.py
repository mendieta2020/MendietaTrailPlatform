"""
core/tests_p1_external_identity.py

PR-X4: ExternalIdentity Linking API — tenancy isolation + functional tests.

Test categories:
  1. Functional: create linked identity, create unlinked identity, list, retrieve, patch, delete.
  2. Tenancy isolation (Ley 1 — fail-closed):
     - cross_org_list_403       — org_B coach targeting org_A → 403
     - cross_org_detail_404     — coach_A cannot see coach_B's identity
     - cross_org_write_403      — org_B POST to org_A → 403
     - unauthenticated_401      — no credentials → 401
     - no_membership_403        — user with no Membership → 403
     - inactive_membership_403  — is_active=False Membership → 403
     - athlete_role_cannot_write — role=athlete → 403 on writes
     - cross_alumno_fk_injection — POST with alumno from another coach → 400

All usernames are prefixed "ei_" to avoid collisions with other test modules.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Alumno, ExternalIdentity, Membership, Organization

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _alumno(coach_user, nombre="Athlete", apellido="EI"):
    return Alumno.objects.create(entrenador=coach_user, nombre=nombre, apellido=apellido)


def _identity(alumno, provider="suunto", external_user_id=None):
    uid = external_user_id or f"{provider}-{alumno.id}"
    linked = alumno is not None
    return ExternalIdentity.objects.create(
        provider=provider,
        external_user_id=uid,
        alumno=alumno,
        status=ExternalIdentity.Status.LINKED if linked else ExternalIdentity.Status.UNLINKED,
    )


def _list_url(org_id):
    return f"/api/p1/orgs/{org_id}/external-identities/"


def _detail_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/external-identities/{pk}/"


# ---------------------------------------------------------------------------
# Setup shared across test classes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExternalIdentityFunctional:
    """Functional tests: CRUD behaviour for a properly-authenticated coach."""

    def setup_method(self):
        self.client = APIClient()

        self.org = _org("ei_func_org")
        self.coach = _user("ei_func_coach")
        _membership(self.coach, self.org, "coach")
        self.alumno = _alumno(self.coach, nombre="Func", apellido="Athlete")

    # --- CREATE ---

    def test_create_linked_identity(self):
        """POST with alumno_id → status=linked, linked_at set."""
        self.client.force_authenticate(self.coach)
        r = self.client.post(
            _list_url(self.org.id),
            {"provider": "suunto", "external_user_id": "sn-001", "alumno_id": self.alumno.id},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["provider"] == "suunto"
        assert data["external_user_id"] == "sn-001"
        assert data["alumno_id"] == self.alumno.id
        assert data["status"] == "linked"
        assert data["linked_at"] is not None

    def test_create_unlinked_identity_no_alumno(self):
        """POST without alumno_id → status=unlinked, linked_at=None."""
        self.client.force_authenticate(self.coach)
        r = self.client.post(
            _list_url(self.org.id),
            {"provider": "strava", "external_user_id": "st-unlinked-001"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["status"] == "unlinked"
        assert data["linked_at"] is None
        assert data["alumno_id"] is None

    def test_list_returns_own_identities(self):
        """GET list returns only identities belonging to the coach's alumnos."""
        _identity(self.alumno, provider="suunto", external_user_id="sn-list-1")
        _identity(self.alumno, provider="strava", external_user_id="st-list-2")
        self.client.force_authenticate(self.coach)
        r = self.client.get(_list_url(self.org.id))
        assert r.status_code == status.HTTP_200_OK
        # Response may be paginated ({count, results}) or a plain list.
        body = r.json()
        results = body["results"] if isinstance(body, dict) else body
        assert len(results) == 2

    def test_retrieve_own_identity(self):
        """GET detail returns the identity if it belongs to the coach's alumno."""
        identity = _identity(self.alumno, provider="suunto", external_user_id="sn-retrieve")
        self.client.force_authenticate(self.coach)
        r = self.client.get(_detail_url(self.org.id, identity.id))
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["id"] == identity.id

    def test_patch_updates_external_user_id(self):
        """PATCH external_user_id on an owned identity → 200, field updated."""
        identity = _identity(self.alumno, provider="suunto", external_user_id="sn-patch-before")
        self.client.force_authenticate(self.coach)
        r = self.client.patch(
            _detail_url(self.org.id, identity.id),
            {"external_user_id": "sn-patch-after"},
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["external_user_id"] == "sn-patch-after"
        # alumno and status remain unchanged
        assert r.json()["alumno_id"] == self.alumno.id
        assert r.json()["status"] == "linked"

    def test_delete_identity(self):
        """DELETE removes the identity."""
        identity = _identity(self.alumno, provider="suunto", external_user_id="sn-delete")
        self.client.force_authenticate(self.coach)
        r = self.client.delete(_detail_url(self.org.id, identity.id))
        assert r.status_code == status.HTTP_204_NO_CONTENT
        assert not ExternalIdentity.objects.filter(id=identity.id).exists()


@pytest.mark.django_db
class TestExternalIdentityTenancy:
    """
    Tenancy isolation tests (Ley 1 — fail-closed).

    org_A = target.  org_B = adversary.
    coach_A has active membership in org_A and alumnos.
    coach_B has active membership in org_B only.
    """

    def setup_method(self):
        self.client = APIClient()

        # org_A (target)
        self.org_a = _org("ei_tenant_a")
        self.coach_a = _user("ei_coach_a")
        _membership(self.coach_a, self.org_a, "coach")
        self.alumno_a = _alumno(self.coach_a, nombre="A", apellido="Athlete")

        # org_B (adversary)
        self.org_b = _org("ei_tenant_b")
        self.coach_b = _user("ei_coach_b")
        _membership(self.coach_b, self.org_b, "coach")
        self.alumno_b = _alumno(self.coach_b, nombre="B", apellido="Athlete")

        # Edge cases
        self.no_membership_user = _user("ei_nomembership")
        self.inactive_user = _user("ei_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

        self.athlete_user = _user("ei_athlete_user")
        _membership(self.athlete_user, self.org_a, "athlete")

    def test_cross_org_list_403(self):
        """coach_B targeting org_A list → 403 (no active membership)."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(_list_url(self.org_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_write_403(self):
        """coach_B POSTing to org_A → 403."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(
            _list_url(self.org_a.id),
            {"provider": "suunto", "external_user_id": "hax-001"},
        )
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_alumno_fk_injection_400(self):
        """coach_A trying to link to coach_B's alumno → 400 (queryset rejects it)."""
        self.client.force_authenticate(self.coach_a)
        r = self.client.post(
            _list_url(self.org_a.id),
            {
                "provider": "suunto",
                "external_user_id": "inject-attempt",
                "alumno_id": self.alumno_b.id,  # belongs to coach_b
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_cross_identity_detail_hidden(self):
        """coach_A cannot retrieve an identity that belongs to coach_B's alumno."""
        identity_b = _identity(self.alumno_b, provider="suunto", external_user_id="sn-hidden")
        self.client.force_authenticate(self.coach_a)
        r = self.client.get(_detail_url(self.org_a.id, identity_b.id))
        assert r.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(_list_url(self.org_a.id))
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership anywhere → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(_list_url(self.org_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(_list_url(self.org_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_athlete_role_cannot_create(self):
        """Athlete (role=athlete) cannot create external identities → 403."""
        self.client.force_authenticate(self.athlete_user)
        r = self.client.post(
            _list_url(self.org_a.id),
            {"provider": "suunto", "external_user_id": "athlete-attempt"},
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_athlete_role_cannot_delete(self):
        """Athlete (role=athlete) cannot delete external identities → 403 or 404.

        The queryset filters by alumno__entrenador=request.user (INNER JOIN), so an
        athlete user who has no alumnos will receive 404 (resource not visible) rather
        than 403. Either response is correct: the resource is effectively denied.
        """
        identity = _identity(self.alumno_a, provider="suunto", external_user_id="sn-athlete-del")
        self.client.force_authenticate(self.athlete_user)
        r = self.client.delete(_detail_url(self.org_a.id, identity.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_list_empty_for_coach_with_no_alumnos(self):
        """A coach who has no alumnos gets an empty list (not another coach's data)."""
        lonely_coach = _user("ei_lonely_coach")
        _membership(lonely_coach, self.org_a, "coach")
        # create an identity for coach_a's alumno — must not appear for lonely_coach
        _identity(self.alumno_a, provider="suunto", external_user_id="sn-not-visible")
        self.client.force_authenticate(lonely_coach)
        r = self.client.get(_list_url(self.org_a.id))
        assert r.status_code == status.HTTP_200_OK
        body = r.json()
        results = body["results"] if isinstance(body, dict) else body
        assert results == []
