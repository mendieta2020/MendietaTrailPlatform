from rest_framework.exceptions import NotFound

from core.models import Alumno


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
