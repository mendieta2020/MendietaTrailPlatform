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


class ApiErrorLoggingMiddleware:
    """
    Log estructurado de errores 5xx en DRF/Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(response, "status_code", 200) >= 500:
            self._log_response_error(request, response)
        return response

    def _log_response_error(self, request, response):
        import logging

        logger = logging.getLogger(__name__)
        user = getattr(request, "user", None)
        logger.error(
            "api.response.error",
            extra={
                "path": getattr(request, "path", ""),
                "method": getattr(request, "method", ""),
                "status_code": getattr(response, "status_code", None),
                "tenant_coach_id": getattr(request, "tenant_coach_id", None),
                "user_id": getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None,
            },
        )


class BearerAuthCsrfBypassMiddleware:
    """
    Permite flujos JWT Bearer sin CSRF cuando NO se usan cookies de auth.

    - Si llega Authorization: Bearer <token> y no hay cookies de auth,
      desactivamos la validación CSRF (clientes no-browser).
    - Si hay cookies de auth presentes, dejamos CSRF activo para evitar
      bypass accidental en flujos cookie-based.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.lower().startswith("bearer "):
            request._dont_enforce_csrf_checks = not self._has_auth_cookies(request)
        return self.get_response(request)

    @staticmethod
    def _has_auth_cookies(request):
        from django.conf import settings

        if not getattr(settings, "USE_COOKIE_AUTH", False):
            return False
        access_cookie = request.COOKIES.get(settings.COOKIE_AUTH_ACCESS_NAME)
        refresh_cookie = request.COOKIES.get(settings.COOKIE_AUTH_REFRESH_NAME)
        return bool(access_cookie or refresh_cookie)
