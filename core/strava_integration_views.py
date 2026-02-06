import base64
import datetime
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import urlencode

from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from stravalib.client import Client

from core.utils.logging import safe_extra


logger = logging.getLogger(__name__)
User = get_user_model()


def _state_ttl_seconds() -> int:
    ttl = getattr(settings, "STRAVA_OAUTH_STATE_TTL_SECONDS", 600)
    try:
        ttl_int = int(ttl)
    except (TypeError, ValueError):
        ttl_int = 600
    return ttl_int if ttl_int > 0 else 600


def _state_signature(payload_b64: str) -> str:
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def build_strava_oauth_state(*, user_id: int) -> str:
    payload = {
        "uid": int(user_id),
        "ts": int(time.time()),
        "nonce": secrets.token_urlsafe(12),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = _state_signature(payload_b64)
    return f"{payload_b64}.{sig}"


def _decode_state(state: str | None) -> tuple[dict | None, str | None]:
    if not state:
        return None, "missing_params"
    if "." not in state:
        return None, "invalid_state"
    payload_b64, signature = state.rsplit(".", 1)
    expected = _state_signature(payload_b64)
    if not hmac.compare_digest(expected, signature):
        return None, "invalid_state"

    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload_json = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except (ValueError, json.JSONDecodeError):
        return None, "invalid_state"

    ts = payload.get("ts")
    uid = payload.get("uid")
    if ts is None or uid is None:
        return None, "invalid_state"

    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return None, "invalid_state"

    if time.time() - ts_int > _state_ttl_seconds():
        return None, "expired"

    return payload, None


def _frontend_redirect_url(*, status: str, reason: str | None = None) -> str:
    base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
    if not base:
        base = "http://localhost:5173"
    query = {"strava": status}
    if reason:
        query["reason"] = reason
    return f"{base}/athlete/integrations?{urlencode(query)}"


class StravaOAuthStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        perfil = getattr(user, "perfil_alumno", None)
        if not perfil:
            logger.warning(
                "strava.oauth.start.forbidden",
                extra=safe_extra({"user_id": user.id, "reason": "not_athlete"}),
            )
            return Response({"detail": "Solo atletas pueden conectar Strava."}, status=403)

        state = build_strava_oauth_state(user_id=user.id)
        callback_url = request.build_absolute_uri(reverse("strava_integration_callback"))

        scope = settings.SOCIALACCOUNT_PROVIDERS.get("strava", {}).get("SCOPE", [])
        auth_params = settings.SOCIALACCOUNT_PROVIDERS.get("strava", {}).get("AUTH_PARAMS", {})
        approval_prompt = auth_params.get("approval_prompt", "force")

        oauth_params = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": ",".join(scope) if isinstance(scope, (list, tuple)) else str(scope),
            "approval_prompt": approval_prompt,
            "state": state,
        }
        oauth_url = f"https://www.strava.com/oauth/authorize?{urlencode(oauth_params)}"

        logger.info(
            "strava.oauth.start",
            extra=safe_extra({"user_id": user.id, "callback_url": callback_url}),
        )
        return Response({"oauth_url": oauth_url})


class StravaOAuthCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        error = request.GET.get("error")
        if error:
            logger.warning(
                "strava.oauth.callback.error",
                extra=safe_extra({"error": error}),
            )
            return redirect(_frontend_redirect_url(status="error", reason=error))

        code = request.GET.get("code")
        state = request.GET.get("state")
        if not code or not state:
            logger.warning(
                "strava.oauth.callback.missing_params",
                extra=safe_extra({"has_code": bool(code), "has_state": bool(state)}),
            )
            return redirect(_frontend_redirect_url(status="error", reason="missing_params"))

        payload, error_reason = _decode_state(state)
        if error_reason:
            logger.warning(
                "strava.oauth.callback.invalid_state",
                extra=safe_extra({"reason": error_reason}),
            )
            return redirect(_frontend_redirect_url(status="error", reason=error_reason))

        user_id = payload.get("uid") if payload else None
        user = (
            User.objects.filter(id=user_id)
            .select_related("perfil_alumno")
            .first()
        )
        if not user or not getattr(user, "perfil_alumno", None):
            logger.warning(
                "strava.oauth.callback.user_missing",
                extra=safe_extra({"user_id": user_id}),
            )
            return redirect(_frontend_redirect_url(status="error", reason="invalid_state"))

        client = Client()
        try:
            token_data = client.exchange_code_for_token(
                client_id=settings.STRAVA_CLIENT_ID,
                client_secret=settings.STRAVA_CLIENT_SECRET,
                code=code,
            )
        except Exception:
            logger.exception(
                "strava.oauth.callback.exchange_failed",
                extra=safe_extra({"user_id": user.id}),
            )
            return redirect(_frontend_redirect_url(status="error", reason="exchange_failed"))

        athlete = token_data.get("athlete") or {}
        athlete_id = athlete.get("id")
        if not athlete_id:
            logger.warning(
                "strava.oauth.callback.missing_athlete_id",
                extra=safe_extra({"user_id": user.id}),
            )
            return redirect(_frontend_redirect_url(status="error", reason="error"))

        expires_at = token_data.get("expires_at")
        expires_at_dt = None
        if expires_at:
            expires_at_dt = timezone.make_aware(datetime.datetime.fromtimestamp(int(expires_at)))

        app_defaults = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "secret": settings.STRAVA_CLIENT_SECRET,
            "name": "Strava",
        }
        social_app, _ = SocialApp.objects.update_or_create(provider="strava", defaults=app_defaults)

        account_defaults = {
            "uid": str(athlete_id),
            "extra_data": athlete,
        }
        social_account, _ = SocialAccount.objects.update_or_create(
            user=user,
            provider="strava",
            defaults=account_defaults,
        )

        token_defaults = {
            "token": token_data.get("access_token", ""),
            "token_secret": token_data.get("refresh_token", ""),
            "expires_at": expires_at_dt,
        }
        SocialToken.objects.update_or_create(
            account=social_account,
            app=social_app,
            defaults=token_defaults,
        )

        alumno = user.perfil_alumno
        alumno.strava_athlete_id = str(athlete_id)
        alumno.save(update_fields=["strava_athlete_id"])

        logger.info(
            "strava.oauth.callback.success",
            extra=safe_extra({"user_id": user.id, "athlete_id": athlete_id}),
        )
        return redirect(_frontend_redirect_url(status="connected"))
