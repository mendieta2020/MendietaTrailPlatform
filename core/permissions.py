from django.conf import settings
from rest_framework.permissions import BasePermission


class IsCoachUser(BasePermission):
    """
    Permite acceso solo a usuarios "coach" (no atletas).
    """
    message = "Acceso restringido a entrenadores."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False):
            return True
        # Si tiene perfil_alumno y NO tiene alumnos a cargo => Es Atleta Puro => False
        # Si tiene perfil_alumno pero TIENE alumnos => Es Coach-Atleta => True
        # Si NO tiene perfil_alumno => Es Coach Puro => True
        is_athlete = hasattr(user, "perfil_alumno")
        has_students = user.alumnos.exists()
        
        if is_athlete and not has_students:
            return False
        return True


class IsAthleteUser(BasePermission):
    """
    Permite acceso a usuarios que son atletas (tienen perfil_alumno).
    """
    message = "Acceso restringido a atletas."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and hasattr(user, "perfil_alumno"))


class SwaggerAccessPermission(BasePermission):
    message = "No autorizado."

    def has_permission(self, request, view) -> bool:
        if not getattr(settings, "SWAGGER_ENABLED", False):
            return False
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))
