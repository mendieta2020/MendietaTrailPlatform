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
