"""
Custom OAuth integration callback handler.

Handles OAuth callbacks for provider integrations (Strava, Garmin, etc),
separate from allauth's social login flow.

Key responsibilities:
1. Validate and consume signed state (CSRF + alumno context)
2. Multi-tenancy check (alumno.usuario must match state.user_id)
3. Exchange authorization code for access token
4. Persist ExternalIdentity with alumno link
5. Update OAuthIntegrationStatus (connected state)
6. Trigger background activity sync
"""
import logging
import requests
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alumno, ExternalIdentity
from .integration_models import OAuthIntegrationStatus
from .oauth_state import validate_and_consume_nonce
from .strava_oauth_views import sanitize_oauth_payload
from .tasks import drain_strava_events_for_athlete

logger = logging.getLogger(__name__)


class IntegrationCallbackView(APIView):
    """
    Custom OAuth integration callback (NOT allauth social login).
    
    GET /api/integrations/{provider}/callback?code=XXX&state=YYY&scope=ZZZ
    
    Validates state, exchanges code for token, links ExternalIdentity to Alumno,
    and redirects to frontend with success/error.
    
    NOTE: This is a PUBLIC endpoint (no IsAuthenticated) because OAuth callback
    happens in browser context without JWT. Security is enforced via signed state.
    """
    permission_classes = []  # Public - state validation provides auth
    
    def get(self, request, provider):
        """Handle OAuth callback for integration flow."""
        
        # Extract callback params
        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")  # Strava sends error if user denies
        
        # Handle user denial
        if error:
            logger.warning("oauth.callback.user_denied", extra={
                "provider": provider,
                "error": error,
                "error_description": request.GET.get("error_description", ""),
            })
            return self._redirect_frontend("error", provider, "user_denied", 
                                         "User denied authorization")
        
        # Validate required params
        if not code or not state:
            logger.error("oauth.callback.missing_params", extra={
                "provider": provider,
                "has_code": bool(code),
                "has_state": bool(state),
            })
            return self._redirect_frontend("error", provider, "invalid_request",
     "Missing code or state parameter")
        
        # Validate and consume state
        payload, state_error = validate_and_consume_nonce(state)
        if state_error:
            logger.error("oauth.callback.invalid_state", extra={
                "provider": provider,
                "error": state_error,
            })
            return self._redirect_frontend("error", provider, state_error,
                                         f"Invalid state: {state_error}")
        
        # Extract state payload
        user_id = payload.get("user_id")
        alumno_id = payload.get("alumno_id")
        state_provider = payload.get("provider")
        
        # Validate provider match
        if state_provider != provider:
            logger.error("oauth.callback.provider_mismatch", extra={
                "url_provider": provider,
                "state_provider": state_provider,
            })
            return self._redirect_frontend("error", provider, "provider_mismatch",
                                         "Provider mismatch")
        
        # Validate alumno_id exists (integration flow requires it)
        if not alumno_id:
            logger.error("oauth.callback.missing_alumno_id", extra={
                "provider": provider,
                "user_id": user_id,
                "state_payload": sanitize_oauth_payload(payload),
            })
            return self._redirect_frontend("error", provider, "missing_context",
                                         "Integration context missing")
        
        # Fetch alumno
        try:
            alumno = Alumno.objects.select_related('usuario').get(id=alumno_id)
        except Alumno.DoesNotExist:
            logger.error("oauth.callback.alumno_not_found", extra={
                "provider": provider,
                "alumno_id": alumno_id,
            })
            return self._redirect_frontend("error", provider, "alumno_not_found",
                                         "Athlete profile not found")
        
        # CRITICAL: Multi-tenancy check (fail-closed)
        if alumno.usuario_id != user_id:
            logger.error("oauth.callback.alumno_user_mismatch", extra={
                "provider": provider,
                "state_user_id": user_id,
                "state_alumno_id": alumno_id,
                "actual_alumno_usuario_id": alumno.usuario_id,
            })
            return self._redirect_frontend("error", provider, "unauthorized",
                                         "Unauthorized access attempt")
        
        # Provider-specific token exchange
        if provider == "strava":
            return self._handle_strava_callback(request, alumno, code, payload)
        else:
            logger.error("oauth.callback.unsupported_provider", extra={
                "provider": provider,
            })
            return self._redirect_frontend("error", provider, "unsupported_provider",
                                         f"Provider {provider} not yet supported")
    
    def _handle_strava_callback(self, request, alumno, code, state_payload):
        """Handle Strava-specific callback logic."""
        provider = "strava"
        
        # Get callback URI from state (for token exchange)
        callback_uri = state_payload.get("redirect_uri", "")
        if not callback_uri:
            # Fallback: reconstruct from settings
            callback_uri = getattr(settings, 'STRAVA_INTEGRATION_CALLBACK_URI', None)
            if not callback_uri:
                public_base = getattr(settings, 'PUBLIC_BASE_URL', 'http://localhost:8000')
                callback_uri = f"{public_base}/api/integrations/strava/callback"
        
        # Exchange code for token
        try:
            token_data = self._exchange_strava_code_for_token(code, callback_uri)
        except Exception as e:
            logger.error("oauth.callback.token_exchange_failed", extra={
                "provider": provider,
                "alumno_id": alumno.id,
                "error": str(e),
            })
            return self._redirect_frontend("error", provider, "token_exchange_failed",
                                         "Failed to exchange authorization code")
        
        # Extract athlete data from token response
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token", "")
        expires_at_timestamp = token_data.get("expires_at")
        athlete_data = token_data.get("athlete", {})
        athlete_id = athlete_data.get("id")
        
        # Validate required fields
        if not access_token or not athlete_id:
            logger.error("oauth.callback.invalid_token_response", extra={
                "provider": provider,
                "alumno_id": alumno.id,
                "has_access_token": bool(access_token),
                "has_athlete_id": bool(athlete_id),
            })
            return self._redirect_frontend("error", provider, "invalid_token_response",
                                         "Invalid token response from Strava")
        
        # Parse expires_at
        expires_at = None
        if expires_at_timestamp:
            try:
                expires_at = datetime.fromtimestamp(int(expires_at_timestamp), tz=dt_timezone.utc)
            except (ValueError, TypeError):
                logger.warning("oauth.callback.invalid_expires_at", extra={
                    "provider": provider,
                    "expires_at_timestamp": expires_at_timestamp,
                })
        
        # Persist ExternalIdentity (idempotent upsert)
        external_user_id = str(int(athlete_id))
        identity, created = ExternalIdentity.objects.update_or_create(
            provider=ExternalIdentity.Provider.STRAVA,
            external_user_id=external_user_id,
            defaults={
                "alumno": alumno,
                "status": ExternalIdentity.Status.LINKED,
                "linked_at": timezone.now(),
                "profile": sanitize_oauth_payload(athlete_data),  # No tokens in profile
            },
        )
        
        # Backfill legacy strava_athlete_id field on Alumno (optional, for admin)
        if not (alumno.strava_athlete_id or "").strip():
            alumno._skip_signal = True  # Avoid forecast recalc
            alumno.strava_athlete_id = external_user_id
            alumno.save(update_fields=["strava_athlete_id"])
        
        # Update OAuthIntegrationStatus (source of truth for connected state)
        integration_status, _ = OAuthIntegrationStatus.objects.update_or_create(
            alumno=alumno,
            provider=provider,
            defaults={
                "connected": True,
                "athlete_id": external_user_id,
                "expires_at": expires_at,
                "last_sync_at": None,  # Will be updated when first sync completes
                "error_reason": "",
                "error_message": "",
            },
        )
        
        # Trigger background activity sync (async celery task)
        try:
            drain_strava_events_for_athlete.delay(alumno.id)
        except Exception as e:
            logger.warning("oauth.callback.drain_task_failed", extra={
                "provider": provider,
                "alumno_id": alumno.id,
                "error": str(e),
            })
        
        # SUCCESS
        logger.info("oauth.callback.success", extra={
            "provider": provider,
            "alumno_id": alumno.id,
            "athlete_id": external_user_id,
            "identity_created": created,
        })
        
        return self._redirect_frontend("success", provider, athlete_id=external_user_id)
    
    def _exchange_strava_code_for_token(self, code, redirect_uri):
        """
        Exchange Strava authorization code for access token.
        
        Returns dict with: access_token, refresh_token, expires_at, athlete{...}
        """
        token_url = "https://www.strava.com/oauth/token"
        data = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }
        
        response = requests.post(token_url, data=data, timeout=10)
        
        # Log sanitized response for debugging
        logger.debug("oauth.token_exchange.response", extra={
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body": sanitize_oauth_payload(response.json() if response.ok else response.text),
        })
        
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx
        
        return response.json()
    
    def _redirect_frontend(self, status_result, provider, error_code=None, error_message=None, athlete_id=None):
        """
        Redirect to frontend with OAuth callback result.
        
        Args:
            status: "success" or "error"
            provider: Provider ID (e.g., "strava")
            error_code: Error code if status="error"
            error_message: Human-readable error message
            athlete_id: External user ID if status="success"
        """
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        callback_path = "/integrations/callback"  # Frontend route
        
        params = {
            "status": status_result,
            "provider": provider,
        }
        
        if status_result == "error":
            params["error"] = error_code or "unknown_error"
            params["message"] = error_message or "An error occurred"
        elif status_result == "success" and athlete_id:
            params["athlete_id"] = athlete_id
        
        redirect_url = f"{frontend_url}{callback_path}?{urlencode(params)}"
        
        return redirect(redirect_url)
