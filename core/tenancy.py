from __future__ import annotations

from rest_framework.exceptions import NotFound, PermissionDenied

from core.models import Alumno


def require_athlete_for_user(*, user, athlete_id: int | str, allow_staff: bool = True) -> Alumno:
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")
    try:
        athlete_id_int = int(athlete_id)
    except (TypeError, ValueError):
        raise NotFound("Athlete not found")

    if allow_staff and getattr(user, "is_staff", False):
        try:
            return Alumno.objects.get(pk=athlete_id_int)
        except Alumno.DoesNotExist as exc:
            raise NotFound("Athlete not found") from exc

    if hasattr(user, "perfil_alumno"):
        perfil = getattr(user, "perfil_alumno", None)
        if not perfil or int(perfil.id) != athlete_id_int:
            raise NotFound("Athlete not found")
        return perfil

    try:
        return Alumno.objects.get(pk=athlete_id_int, entrenador=user)
    except Alumno.DoesNotExist as exc:
        raise NotFound("Athlete not found") from exc
