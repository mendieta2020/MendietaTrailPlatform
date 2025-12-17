class TenantContextMiddleware:
    """
    Middleware liviano para exponer el "tenant" efectivo del request.

    Estrategia actual (FASE 1B): Tenant = coach (User.id).
    - Si el usuario es atleta (`user.perfil_alumno`), el tenant es su `entrenador_id`.
    - Si el usuario es coach, el tenant es su propio `user.id`.

    Nota: la validación/bloqueo de acceso cross-tenant se hace en ViewSets/permissions
    (y en APIViews como PMC), este middleware solo fija contexto.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant_coach_id = None
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            if hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None):
                request.tenant_coach_id = getattr(user.perfil_alumno, "entrenador_id", None)
            else:
                request.tenant_coach_id = getattr(user, "id", None)
        return self.get_response(request)

