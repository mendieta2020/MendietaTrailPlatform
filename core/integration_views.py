"""
OAuth integration management views.

Provides endpoints for:
- POST /api/integrations/{provider}/start - Initiate OAuth flow
- GET /api/integrations/status - Get integration status for all providers (student)
- GET /api/coach/athletes/<alumno_id>/integrations/status - Get integration status for athlete (coach)
"""
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


from .integration_models import OAuthIntegrationStatus
from .models import Alumno
from .oauth_state import generate_oauth_state
from .providers import PROVIDERS, get_available_providers

logger = logging.getLogger(__name__)


class IntegrationStartView(APIView):
    """
    POST /api/integrations/{provider}/start
    
    Initiates OAuth flow for a provider.
    - Validates provider exists and is enabled
    - Validates user has Alumno profile
    - Generates OAuth state with nonce
    - Returns OAuth authorization URL for frontend redirect
    
    Required: user must be authenticated and have an Alumno profile (athlete role).
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, provider):
        # Validate provider exists
        provider_obj = PROVIDERS.get(provider)
        if not provider_obj:
            return Response(
                {"error": "invalid_provider", "message": f"Provider '{provider}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Validate provider is enabled
        if not provider_obj.enabled:
            return Response(
                {"error": "provider_disabled", "message": f"Provider '{provider}' is not yet available"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate user has Alumno profile
        try:
            alumno = Alumno.objects.get(usuario=request.user)
        except Alumno.DoesNotExist:
            return Response(
                {"error": "athlete_not_found", "message": "No athlete profile found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # For Strava, use allauth's OAuth flow (existing, battle-tested)
        # We don't use custom state/nonce here to keep allauth unchanged
        if provider == "strava":
            # Use configured redirect URI (ngrok/prod) instead of request host
            # This prevents "testserver" issues in tests and ensures consistent OAuth callback
            callback_uri = settings.STRAVA_REDIRECT_URI
            
            if not callback_uri:
                logger.error("oauth.start.missing_redirect_uri", extra={"provider": provider})
                return Response(
                    {"error": "server_misconfigured", "message": "OAuth redirect URI not configured in settings"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            
            client_id = settings.STRAVA_CLIENT_ID
            if not client_id:
                return Response(
                    {"error": "provider_not_configured", "message": "Strava client ID not configured"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            
            # Build Strava OAuth URL (allauth compatible)
            strava_authorize_url = "https://www.strava.com/oauth/authorize"
            params = {
                "client_id": client_id,
                "redirect_uri": callback_uri,
                "response_type": "code",
                "scope": "read,activity:read_all,profile:read_all",
                "approval_prompt": "force",
            }
            oauth_url = f"{strava_authorize_url}?{urlencode(params)}"
            
            logger.info(
                "oauth.start.success",
                extra={
                    "provider": provider,
                    "user_id": request.user.id,
                    "alumno_id": alumno.id,
                    "redirect_uri": callback_uri,  # Log for debugging
                },
            )
            
            return Response({
                "oauth_url": oauth_url,
                "provider": provider,
            })
        
        # For other providers, return not implemented
        return Response(
            {"error": "provider_not_implemented", "message": f"OAuth flow for {provider} coming soon"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class IntegrationStatusView(APIView):
    """
    GET /api/integrations/status
    
    Returns OAuth integration status for all providers for the authenticated athlete.
    Only accessible by athlete users (must have Alumno profile).
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get athlete profile for authenticated user
        try:
            alumno = Alumno.objects.get(usuario=request.user)
        except Alumno.DoesNotExist:
            return Response(
                {"error": "athlete_not_found", "message": "No athlete profile found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Fetch all integration statuses for this athlete
        statuses = OAuthIntegrationStatus.objects.filter(alumno=alumno)
        status_map = {s.provider: s for s in statuses}
        
        # Build response for all providers
        integrations = []
        for provider_data in get_available_providers():
            provider_id = provider_data["id"]
            integration_status = status_map.get(provider_id)
            
            if integration_status and integration_status.connected:
                # Connected integration
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "connected": True,
                    "athlete_id": integration_status.athlete_id,
                    "expires_at": integration_status.expires_at.isoformat() if integration_status.expires_at else None,
                    "last_sync_at": integration_status.last_sync_at.isoformat() if integration_status.last_sync_at else None,
                    "error_reason": None,
                })
            elif integration_status and not integration_status.connected:
                # Failed integration (has error)
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "connected": False,
                    "athlete_id": None,
                    "expires_at": None,
                    "last_sync_at": None,
                    "error_reason": integration_status.error_reason or "unknown",
                    "error_message": integration_status.error_message or "",
                    "last_error_at": integration_status.last_error_at.isoformat() if integration_status.last_error_at else None,
                })
            else:
                # Not connected, no attempt yet
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "connected": False,
                    "athlete_id": None,
                    "expires_at": None,
                    "last_sync_at": None,
                    "error_reason": None,
                })
        
        return Response({
            "integrations": integrations,
            "athlete_id": alumno.id,
        })


class CoachAthleteIntegrationStatusView(APIView):
    """
    GET /api/coach/athletes/<alumno_id>/integrations/status
    
    Returns OAuth integration status for a specific athlete.
    Coach-scoped: only accessible by coach who owns the athlete (multi-tenant enforced).
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, alumno_id):
        # Get the athlete
        try:
            alumno = Alumno.objects.select_related("entrenador").get(pk=alumno_id)
        except Alumno.DoesNotExist:
            return Response(
                {"error": "athlete_not_found", "message": "Athlete not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Enforce coach ownership (fail-closed tenancy)
        # Only the coach who owns this athlete can see integration status
        if request.user != alumno.entrenador:
            logger.warning(
                "coach.athlete_integration_status.unauthorized",
                extra={
                    "request_user_id": request.user.id,
                    "alumno_id": alumno_id,
                    "alumno_coach_id": alumno.entrenador.id if alumno.entrenador else None,
                },
            )
            return Response(
                {"error": "forbidden", "message": "Access denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Fetch all integration statuses for this athlete
        statuses = OAuthIntegrationStatus.objects.filter(alumno=alumno)
        status_map = {s.provider: s for s in statuses}
        
        # Build response for all providers
        integrations = []
        for provider_data in get_available_providers():
            provider_id= provider_data["id"]
            integration_status = status_map.get(provider_id)
            
            if integration_status and integration_status.connected:
                # Connected integration
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "connected": True,
                    "athlete_id": integration_status.athlete_id,
                    "last_sync_at": integration_status.last_sync_at.isoformat() if integration_status.last_sync_at else None,
                })
            else:
                # Not connected or failed
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "connected": False,
                    "athlete_id": None,
                    "last_sync_at": None,
                })
        
        return Response({
            "integrations": integrations,
            "athlete_id": alumno.id,
            "athlete_name": alumno.nombre,
        })
