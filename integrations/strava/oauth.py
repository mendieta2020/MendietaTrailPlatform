import json
import logging
from http import HTTPStatus

from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client, OAuth2Error
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView, OAuth2LoginView
from allauth.socialaccount.providers.strava.views import StravaOAuth2Adapter
from core.utils.logging import sanitize_secrets

logger = logging.getLogger("allauth.socialaccount.providers.strava")

sanitize_oauth_payload = sanitize_secrets


class LoggedOAuth2Client(OAuth2Client):
    """
    Wrapper de OAuth2Client que loguea el intercambio code->token con detalles útiles
    (status, content-type, redirect_uri) y cuerpo sanitizado.
    """

    def get_access_token(self, code, pkce_code_verifier=None, extra_data=None):
        data = {
            "redirect_uri": self.callback_url,
            "grant_type": "authorization_code",
            "code": code,
        }
        if self.basic_auth:
            import requests

            auth = requests.auth.HTTPBasicAuth(self.consumer_key, self.consumer_secret)
        else:
            auth = None
            data.update(
                {
                    self.client_id_parameter: self.consumer_key,
                    "client_secret": self.consumer_secret,
                }
            )
        if extra_data:
            data.update(extra_data)
        params = None
        self._strip_empty_keys(data)
        url = self.access_token_url
        if self.access_token_method == "GET":  # nosec
            params = data
            data = None
        if data and pkce_code_verifier:
            data["code_verifier"] = pkce_code_verifier

        resp = (
            get_social_adapter()
            .get_requests_session()
            .request(
                self.access_token_method,
                url,
                params=params,
                data=data,
                headers=self.headers,
                auth=auth,
            )
        )

        content_type = resp.headers.get("content-type", "")
        body_preview = None
        try:
            if content_type.split(";")[0] == "application/json" or (resp.text or "")[:2] == '{"':
                body_preview = sanitize_secrets(resp.json())
            else:
                body_preview = sanitize_secrets(resp.text)
        except Exception:
            body_preview = "<unparseable>"

        logger.info("strava.http.request", extra={
            "method": self.access_token_method,
            "url_path": "/oauth/token",
            "status_code": resp.status_code,
        })
        logger.debug(
            "Strava token exchange: status=%s method=%s url=%s redirect_uri=%s content_type=%s body=%s",
            resp.status_code,
            self.access_token_method,
            url,
            self.callback_url,
            content_type,
            body_preview,
        )

        access_token = None
        if resp.status_code in [HTTPStatus.OK, HTTPStatus.CREATED]:
            if content_type.split(";")[0] == "application/json" or (resp.text or "")[:2] == '{"':
                access_token = resp.json()
            else:
                from urllib.parse import parse_qsl

                access_token = dict(parse_qsl(resp.text))

        if not access_token or "access_token" not in access_token:
            # Mantener el comportamiento de allauth, pero con logs enriquecidos arriba.
            raise OAuth2Error("Error retrieving access token: %s" % resp.content)

        # Evitar que tokens entren a logs vía repr() accidental
        try:
            logger.debug("Strava token OK (sanitized)=%s", json.dumps(sanitize_secrets(access_token)))
        except Exception:
            logger.debug("Strava token OK (sanitized)=%s", sanitize_secrets(access_token))

        return access_token

class LoggedStravaOAuth2Adapter(StravaOAuth2Adapter):
    client_class = LoggedOAuth2Client

# Vistas que reemplazan a allauth strava por defecto (mismas URLs/names que allauth)
oauth2_login = OAuth2LoginView.adapter_view(LoggedStravaOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(LoggedStravaOAuth2Adapter)


def refresh_strava_token(credential):
    """
    Refresh a Strava access token using the stored refresh_token.

    Concurrent-safe: acquires select_for_update() before checking expiry so
    only one worker calls Strava when multiple tasks race on the same expired
    credential.  If the lock reveals the token is already fresh (a concurrent
    worker beat us here), returns the current access_token immediately.

    Updates both OAuthCredential (primary store) and SocialToken (allauth
    mirror) so the legacy obtener_cliente_strava path stays in sync.

    Args:
        credential: OAuthCredential instance pre-fetched by the caller.

    Returns:
        str — the new (or already-fresh) access_token.

    Raises:
        requests.exceptions.HTTPError: from Strava (401 = bad refresh token,
            429 = rate-limited). Caller should treat 401 as "user must reconnect".
        RuntimeError: no SocialApp config for strava.
        Exception: any other Strava API or DB error.

    Structured log events emitted:
        strava.token.refreshed.ok           — success or already-fresh under lock
        strava.token.refreshed.strava_401   — invalid/revoked refresh_token
        strava.token.refreshed.rate_limited — Strava 429
        strava.token.refreshed.unexpected_error — all other failures
    """
    import datetime

    import requests as _requests
    from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
    from django.db import transaction
    from django.utils import timezone
    from stravalib.client import Client

    from core.models import OAuthCredential  # noqa: PLC0415 — integrations may import core

    alumno_id = credential.alumno_id

    with transaction.atomic():
        locked = (
            OAuthCredential.objects
            .select_for_update()
            .select_related("alumno")
            .get(pk=credential.pk)
        )

        now = timezone.now()
        buffer = datetime.timedelta(seconds=60)
        if locked.expires_at is not None and now < (locked.expires_at - buffer):
            logger.info(
                "strava.token.refreshed.ok",
                extra={
                    "event_name": "strava.token.refreshed.ok",
                    "alumno_id": alumno_id,
                    "outcome": "ok",
                    "reason_code": "ALREADY_FRESH",
                },
            )
            return locked.access_token

        app_config = SocialApp.objects.filter(provider="strava").first()
        if not app_config:
            raise RuntimeError("No SocialApp configured for strava — cannot refresh token")

        try:
            temp = Client()
            resp = temp.refresh_access_token(
                client_id=app_config.client_id,
                client_secret=app_config.secret,
                refresh_token=locked.refresh_token,
            )
        except _requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 401:
                event = "strava.token.refreshed.strava_401"
                reason = "REFRESH_TOKEN_INVALID"
            elif status == 429:
                event = "strava.token.refreshed.rate_limited"
                reason = "STRAVA_RATE_LIMIT"
            else:
                event = "strava.token.refreshed.unexpected_error"
                reason = f"HTTP_{status}"
            logger.exception(
                event,
                extra={
                    "event_name": event,
                    "alumno_id": alumno_id,
                    "outcome": "fail",
                    "reason_code": reason,
                    "http_status": status,
                },
            )
            raise
        except Exception:
            logger.exception(
                "strava.token.refreshed.unexpected_error",
                extra={
                    "event_name": "strava.token.refreshed.unexpected_error",
                    "alumno_id": alumno_id,
                    "outcome": "fail",
                    "reason_code": "UNEXPECTED_ERROR",
                },
            )
            raise

        new_access = resp["access_token"]
        new_refresh = resp.get("refresh_token", locked.refresh_token)
        new_expires_at = timezone.make_aware(
            datetime.datetime.fromtimestamp(resp["expires_at"])
        )

        OAuthCredential.objects.filter(pk=locked.pk).update(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_at=new_expires_at,
        )

        # Mirror to SocialToken so the legacy allauth path stays in sync.
        if locked.alumno.usuario_id is not None:
            sa = SocialAccount.objects.filter(
                user_id=locked.alumno.usuario_id, provider="strava"
            ).first()
            if sa:
                SocialToken.objects.filter(account=sa).update(
                    token=new_access,
                    token_secret=new_refresh,
                    expires_at=new_expires_at,
                )

        logger.info(
            "strava.token.refreshed.ok",
            extra={
                "event_name": "strava.token.refreshed.ok",
                "alumno_id": alumno_id,
                "outcome": "ok",
                "reason_code": "TOKEN_REFRESHED",
            },
        )
        return new_access
