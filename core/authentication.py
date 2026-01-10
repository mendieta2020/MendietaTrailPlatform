from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """Autenticación JWT usando cookie HttpOnly (modo transición)."""

    def authenticate(self, request):
        if not getattr(settings, "USE_COOKIE_AUTH", False):
            return None

        cookie_name = getattr(settings, "COOKIE_AUTH_ACCESS_NAME", "mt_access")
        raw_token = request.COOKIES.get(cookie_name)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
