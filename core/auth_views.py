from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def _get_lifetime_seconds(lifetime):
    try:
        return int(lifetime.total_seconds())
    except Exception:
        return None


def _cookie_base_kwargs():
    return {
        "httponly": True,
        "secure": getattr(settings, "COOKIE_AUTH_SECURE", False),
        "samesite": getattr(settings, "COOKIE_AUTH_SAMESITE", "Lax"),
        "domain": getattr(settings, "COOKIE_AUTH_DOMAIN", None),
        "path": "/",
    }


def _set_auth_cookie(response, name, value, max_age):
    if not value:
        return
    kwargs = _cookie_base_kwargs()
    if max_age is not None:
        kwargs["max_age"] = max_age
    response.set_cookie(name, value, **kwargs)


def _set_auth_cookies(response, *, access=None, refresh=None):
    access_lifetime = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME")
    refresh_lifetime = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME")
    _set_auth_cookie(
        response,
        settings.COOKIE_AUTH_ACCESS_NAME,
        access,
        _get_lifetime_seconds(access_lifetime),
    )
    _set_auth_cookie(
        response,
        settings.COOKIE_AUTH_REFRESH_NAME,
        refresh,
        _get_lifetime_seconds(refresh_lifetime),
    )


def _clear_auth_cookies(response):
    response.delete_cookie(
        settings.COOKIE_AUTH_ACCESS_NAME,
        domain=settings.COOKIE_AUTH_DOMAIN,
        path="/",
    )
    response.delete_cookie(
        settings.COOKIE_AUTH_REFRESH_NAME,
        domain=settings.COOKIE_AUTH_DOMAIN,
        path="/",
    )


class CookieTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if getattr(settings, "USE_COOKIE_AUTH", False) and response.status_code == 200:
            _set_auth_cookies(
                response,
                access=response.data.get("access"),
                refresh=response.data.get("refresh"),
            )
        return response


class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if getattr(settings, "USE_COOKIE_AUTH", False) and "refresh" not in request.data:
            refresh_cookie = request.COOKIES.get(settings.COOKIE_AUTH_REFRESH_NAME)
            if refresh_cookie:
                data = request.data.copy()
                data["refresh"] = refresh_cookie
                request._full_data = data

        response = super().post(request, *args, **kwargs)
        if getattr(settings, "USE_COOKIE_AUTH", False) and response.status_code == 200:
            _set_auth_cookies(
                response,
                access=response.data.get("access"),
                refresh=response.data.get("refresh"),
            )
        return response


class CookieLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({"detail": "logout"}, status=200)
        if getattr(settings, "USE_COOKIE_AUTH", False):
            _clear_auth_cookies(response)
        return response


class SessionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "username": request.user.username,
                "id": request.user.id,
            }
        )
