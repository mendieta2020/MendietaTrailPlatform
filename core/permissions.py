from rest_framework.permissions import BasePermission


class IsCoachUser(BasePermission):
    """
    Permite acceso solo a usuarios "coach" (no atletas).

    Heurística actual del proyecto:
    - Si el User tiene `perfil_alumno`, lo tratamos como atleta.
    - Staff siempre permitido.
    """

    message = "No autorizado."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False):
            return True
        return not hasattr(user, "perfil_alumno")

