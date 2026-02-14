from rest_framework.exceptions import NotFound

from core.models import Alumno, Equipo


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
