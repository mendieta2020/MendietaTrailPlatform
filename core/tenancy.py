from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import NotFound

from core.models import Alumno, Equipo, Membership


_NOT_FOUND_MESSAGE = "Athlete not found"


def require_athlete_for_user(*, user, athlete_id) -> Alumno:
    try:
        athlete_id_int = int(athlete_id)
    except (TypeError, ValueError) as exc:
        raise NotFound(_NOT_FOUND_MESSAGE) from exc

    if not user or not getattr(user, "is_authenticated", False):
        raise NotFound(_NOT_FOUND_MESSAGE)

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        try:
            return Alumno.objects.select_related("equipo", "entrenador").get(id=athlete_id_int)
        except Alumno.DoesNotExist as exc:
            raise NotFound(_NOT_FOUND_MESSAGE) from exc

    if hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None):
        perfil = user.perfil_alumno
        if int(perfil.id) != athlete_id_int:
            raise NotFound(_NOT_FOUND_MESSAGE)
        return perfil

    try:
        return Alumno.objects.select_related("equipo").get(id=athlete_id_int, entrenador=user)
    except Alumno.DoesNotExist as exc:
        raise NotFound(_NOT_FOUND_MESSAGE) from exc


def require_athlete_for_coach(*, user, athlete_id) -> Alumno:
    """
    Coach-strict resolver: returns Alumno ONLY if entrenador=user.
    NO fallback to "self" access (avoids athletes accessing coach APIs).
    """
    try:
        athlete_id_int = int(athlete_id)
    except (TypeError, ValueError) as exc:
        raise NotFound(_NOT_FOUND_MESSAGE) from exc

    if not user or not getattr(user, "is_authenticated", False):
        raise NotFound(_NOT_FOUND_MESSAGE)

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        try:
            return Alumno.objects.select_related("equipo", "entrenador").get(id=athlete_id_int)
        except Alumno.DoesNotExist as exc:
            raise NotFound(_NOT_FOUND_MESSAGE) from exc
            
    # Strict check: MUST be the coach
    try:
        return Alumno.objects.select_related("equipo").get(id=athlete_id_int, entrenador=user)
    except Alumno.DoesNotExist as exc:
        raise NotFound(_NOT_FOUND_MESSAGE) from exc


class CoachTenantAPIViewMixin:
    def require_athlete(self, request, athlete_id) -> Alumno:
        if getattr(self, "swagger_fake_view", False):
            try:
                athlete_id_int = int(athlete_id)
            except (TypeError, ValueError):
                athlete_id_int = 0
            return Alumno(id=athlete_id_int)
        return require_athlete_for_coach(user=request.user, athlete_id=athlete_id)

    def require_group(self, request, group_id) -> Equipo:
        if getattr(self, "swagger_fake_view", False):
            try:
                group_id_int = int(group_id)
            except (TypeError, ValueError):
                group_id_int = 0
            return Equipo(id=group_id_int)
        try:
            return Equipo.objects.get(id=int(group_id), entrenador=request.user)
        except Equipo.DoesNotExist as exc:
            raise NotFound("Group not found") from exc


# ==============================================================================
#  ORGANIZATION-FIRST TENANCY GATE — P1 (PR-102)
#  These functions are for new P1+ views only.
#  Do not use on existing entrenador-scoped views.
# ==============================================================================

def get_active_membership(user, organization_id: int) -> Membership:
    """
    Resolve an active Membership for (user, organization).

    Fail-closed: raises PermissionDenied if no active membership exists.
    Never returns None — callers can assume a valid Membership on success.

    Usage:
        membership = get_active_membership(request.user, org_id)
        # Proceeds only if membership is active
    """
    try:
        return Membership.objects.get(
            user=user,
            organization_id=organization_id,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active membership for this organization.")


def require_role(user, organization_id: int, allowed_roles: list) -> Membership:
    """
    Resolve membership and verify the user has one of the allowed roles.

    Fail-closed: raises PermissionDenied on missing membership OR wrong role.

    Usage:
        membership = require_role(request.user, org_id, ["owner", "coach"])
    """
    membership = get_active_membership(user, organization_id)
    if membership.role not in allowed_roles:
        raise PermissionDenied(
            f"Role '{membership.role}' is not authorized for this action."
        )
    return membership


class OrgTenantMixin:
    """
    DRF ViewSet mixin for organization-scoped endpoints.

    Resolves and caches the active Membership on each request.
    Subclasses access `self.membership` and `self.organization` after
    calling `self.resolve_membership(org_id)`.

    Replaces the legacy CoachTenantAPIViewMixin for new P1+ views.
    Do not use this on existing views.
    """

    def resolve_membership(self, organization_id: int) -> Membership:
        membership = get_active_membership(self.request.user, organization_id)
        self.membership = membership
        self.organization = membership.organization
        return membership
