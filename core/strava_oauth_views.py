import json
import logging
from http import HTTPStatus

from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client, OAuth2Error
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView, OAuth2LoginView
from allauth.socialaccount.providers.strava.views import StravaOAuth2Adapter
from django.http import HttpResponseForbidden

logger = logging.getLogger("allauth.socialaccount.providers.strava")

_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "token_type",
    "expires_at",
    "expires_in",
    # Strava también puede devolver athlete data; no es secreto pero puede ser grande.
}


def _truncate(s: str, max_len: int = 400) -> str:
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def sanitize_oauth_payload(obj):
    """
    Sanitiza payloads (dict/list/str/bytes) para logging:
    - redacción de tokens
    - truncado de strings largas
    """
    if obj is None:
        return None

    # Preservar primitivos JSON (para no “stringificar” ints/bools en logs/tests)
    if isinstance(obj, (int, float, bool)):
        return obj

    if isinstance(obj, (bytes, bytearray)):
        try:
            obj = obj.decode("utf-8", errors="replace")
        except Exception:
            return "<binary>"

    if isinstance(obj, str):
        return _truncate(obj)

    if isinstance(obj, list):
        return [sanitize_oauth_payload(x) for x in obj[:50]]

    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:200]:
            if k in _SENSITIVE_KEYS:
                out[k] = "<redacted>"
            else:
                out[k] = sanitize_oauth_payload(v)
        return out

    return _truncate(str(obj), max_len=200)


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
                body_preview = sanitize_oauth_payload(resp.json())
            else:
                body_preview = sanitize_oauth_payload(resp.text)
        except Exception:
            body_preview = "<unparseable>"

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
            logger.debug("Strava token OK (sanitized)=%s", json.dumps(sanitize_oauth_payload(access_token)))
        except Exception:
            logger.debug("Strava token OK (sanitized)=%s", sanitize_oauth_payload(access_token))

        return access_token


class LoggedStravaOAuth2Adapter(StravaOAuth2Adapter):
    client_class = LoggedOAuth2Client


def can_start_strava_oauth(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None) is not None


def _reject_non_athlete(request):
    if can_start_strava_oauth(getattr(request, "user", None)):
        return None
    return HttpResponseForbidden("Solo el alumno autenticado puede conectar Strava.")


_oauth2_login_view = OAuth2LoginView.adapter_view(LoggedStravaOAuth2Adapter)
_oauth2_callback_view = OAuth2CallbackView.adapter_view(LoggedStravaOAuth2Adapter)


def oauth2_login(request, *args, **kwargs):
    rejection = _reject_non_athlete(request)
    if rejection:
        return rejection
    return _oauth2_login_view(request, *args, **kwargs)


def oauth2_callback(request, *args, **kwargs):
    rejection = _reject_non_athlete(request)
    if rejection:
        return rejection
    return _oauth2_callback_view(request, *args, **kwargs)
