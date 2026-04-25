from django.conf import settings
from django.contrib.auth import authenticate as _django_authenticate
from django.contrib.auth import get_user_model as _get_user_model_early
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import serializers as _drf_serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.models import Membership

_EarlyUser = _get_user_model_early()


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


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Drop-in replacement for SimpleJWT's default serializer.

    Accepts ``email`` + ``password`` instead of ``username`` + ``password``.
    Looks up the user by email, authenticates with Django's ModelBackend
    (which requires the opaque ``username``), then issues the token pair.

    Backward compat: Fernando's account (and any legacy username-based accounts)
    continue to work because the lookup is done via email — the stored username
    is never exposed to the caller.
    """
    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")

        # 1. Look up user by email — oldest account (lowest id) wins on duplicate email;
        #    .filter().first() avoids MultipleObjectsReturned if two accounts share the address.
        user_obj = _EarlyUser.objects.filter(email__iexact=email).order_by('id').first()
        if user_obj is None:
            raise _drf_serializers.ValidationError(
                {"detail": "No active account found with the given credentials"}
            )

        # 2. Authenticate via Django backend (requires username, not email)
        user = _django_authenticate(
            request=self.context.get("request"),
            username=user_obj.username,
            password=password,
        )
        if user is None or not user.is_active:
            raise _drf_serializers.ValidationError(
                {"detail": "No active account found with the given credentials"}
            )

        # 3. Issue JWT pair
        self.user = user
        refresh = self.get_token(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class CookieTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES
    serializer_class = EmailTokenObtainPairSerializer

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
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

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
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def post(self, request):
        response = Response({"detail": "logout"}, status=200)
        if getattr(settings, "USE_COOKIE_AUTH", False):
            _clear_auth_cookies(response)
        return response


@method_decorator(ensure_csrf_cookie, name="get")
class SessionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user, is_active=True)
            .select_related("organization")
            .order_by("organization_id")
        )
        membership_list = [
            {
                "org_id": m.organization_id,
                "org_name": m.organization.name,
                "role": m.role,
                "is_active": m.is_active,
            }
            for m in memberships
        ]
        return Response(
            {
                "username": request.user.username,
                "id": request.user.id,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email or "",
                "memberships": membership_list,
            }
        )


# ==============================================================================
# PR-165e: Password reset (request + confirm) — OWASP-compliant
# ==============================================================================

import logging as _logging

from django.conf import settings as _settings
from django.contrib.auth import get_user_model as _get_user_model
from django.core.cache import cache as _cache
from django.utils import timezone as _tz

from rest_framework.permissions import AllowAny as _AllowAny
from rest_framework.views import APIView as _APIView
from rest_framework.response import Response as _Response

from core.models import PasswordResetToken

_logger = _logging.getLogger(__name__)
_User = _get_user_model()


def _send_reset_email(to_email, user_name, reset_url):
    """Send reset email via Resend if API key is set, else console."""
    if _settings.RESEND_API_KEY:
        try:
            import resend
            resend.api_key = _settings.RESEND_API_KEY
            resend.Emails.send({
                "from": _settings.DEFAULT_FROM_EMAIL,
                "to": [to_email],
                "subject": "Restablecé tu contraseña — Quantoryn",
                "html": _build_reset_html(user_name, reset_url),
            })
        except Exception as exc:
            _logger.error("password_reset.email_failed", extra={"exc": str(exc), "outcome": "error"})
    else:
        print(f"\n[DEV] PASSWORD RESET for {to_email}:\n{reset_url}\n")


def _build_reset_html(name, reset_url):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:500px;margin:40px auto;padding:20px;color:#1F2937;">
<h1 style="color:#00D4AA;font-size:22px;">Hola {name},</h1>
<p style="font-size:16px;line-height:1.5;">Recibimos una solicitud para restablecer tu contraseña de Quantoryn.</p>
<p style="font-size:16px;line-height:1.5;">Hacé clic en el botón para crear una nueva:</p>
<div style="margin:32px 0;text-align:center;">
  <a href="{reset_url}" style="background:#00D4AA;color:white;padding:16px 32px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;">
    Restablecer contraseña
  </a>
</div>
<p style="font-size:14px;color:#6B7280;">⏱️ Este enlace expira en 1 hora.</p>
<hr style="border:none;border-top:1px solid #E5E7EB;margin:24px 0;">
<p style="font-size:13px;color:#9CA3AF;">Si no fuiste vos quien pidió esto, ignorá este email. Tu contraseña sigue igual.</p>
<p style="font-size:13px;color:#9CA3AF;">— Equipo Quantoryn</p>
</body></html>"""


def _send_welcome_email(to_email, first_name, org_name, role):
    """Send post-registration welcome email via Resend if configured, else console."""
    role_labels = {
        "athlete": "atleta",
        "coach": "coach",
        "owner": "administrador",
        "staff": "staff",
    }
    role_label = role_labels.get(role, role)
    subject = f"¡Bienvenido a {org_name}!"
    html_body = _build_welcome_html(first_name, org_name, role_label)

    if _settings.RESEND_API_KEY:
        try:
            import resend
            resend.api_key = _settings.RESEND_API_KEY
            resend.Emails.send({
                "from": _settings.DEFAULT_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            })
        except Exception as exc:
            _logger.error("welcome_email.send_failed", extra={"exc": str(exc), "outcome": "error"})
    else:
        print(f"\n[DEV] WELCOME EMAIL for {to_email} ({org_name}):\n{subject}\n")


def _build_welcome_html(first_name, org_name, role_label):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:500px;margin:40px auto;padding:20px;color:#1F2937;">
<h1 style="color:#00D4AA;font-size:22px;">¡Hola {first_name}!</h1>
<p style="font-size:16px;line-height:1.5;">
  Ya estás dentro de <strong>{org_name}</strong> como <strong>{role_label}</strong>.
  Tu equipo ya puede verte.
</p>
<p style="font-size:16px;line-height:1.5;">
  Conectá tu dispositivo para que tus actividades se sincronicen automáticamente y
  tu coach pueda ver tu progreso en tiempo real.
</p>
<div style="margin:32px 0;text-align:center;">
  <a href="https://app.quantoryn.com/dashboard"
     style="background:#00D4AA;color:white;padding:16px 32px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;">
    Ir a mi dashboard
  </a>
</div>
<hr style="border:none;border-top:1px solid #E5E7EB;margin:24px 0;">
<p style="font-size:13px;color:#9CA3AF;">— Equipo Quantoryn</p>
</body></html>"""


class PasswordResetRequestView(_APIView):
    """POST /api/auth/password-reset/request/ — anti-enumeration, rate-limited."""

    permission_classes = [_AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return _Response({"detail": "Email requerido."}, status=400)

        # Rate limit: max 3 attempts per email per hour
        cache_key = f"pwd_reset_rate:{email}"
        attempts = _cache.get(cache_key, 0)
        _cache.set(cache_key, attempts + 1, timeout=3600)

        user = _User.objects.filter(email__iexact=email).first()
        if user and attempts < 3:
            raw_token = PasswordResetToken.create_for_user(user)
            frontend_url = getattr(_settings, "FRONTEND_URL", "http://localhost:5173")
            reset_url = f"{frontend_url}/auth/reset-password/{raw_token}"
            _send_reset_email(email, user.first_name or "Hola", reset_url)
            _logger.info("password_reset.requested", extra={
                "user_id": user.id, "outcome": "sent",
            })

        # Always 200 — anti-enumeration
        return _Response({
            "detail": "Si el email existe en Quantoryn, te enviamos las instrucciones. Revisá tu bandeja de entrada."
        })


class PasswordResetConfirmView(_APIView):
    """POST /api/auth/password-reset/confirm/ — validate token + set new password."""

    permission_classes = [_AllowAny]
    authentication_classes = []

    def post(self, request):
        token = request.data.get("token", "").strip()
        new_password = request.data.get("new_password", "")

        if not token or not new_password:
            return _Response({"detail": "Datos incompletos."}, status=400)
        if len(new_password) < 8:
            return _Response({"detail": "La contraseña debe tener al menos 8 caracteres."}, status=400)

        user = PasswordResetToken.consume(token)
        if not user:
            return _Response({"detail": "Link inválido o expirado. Pedí un nuevo link."}, status=400)

        user.set_password(new_password)
        user.save()

        _logger.info("password_reset.completed", extra={"user_id": user.id, "outcome": "success"})
        return _Response({"detail": "¡Contraseña actualizada! Ya podés iniciar sesión."})
