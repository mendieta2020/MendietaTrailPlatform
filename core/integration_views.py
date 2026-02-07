"""
OAuth integration management views.

Provides endpoints for:
- POST /api/integrations/{provider}/start - Initiate OAuth flow
- GET /api/integrations/status - Get integration status for all providers
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

# Frontend base URL for redirects after OAuth callback
FRONTEND_BASE_URL = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")


class IntegrationStartView(APIView):
    """
    POST /api/integrations/{provider}/start
    
    Initiate OAuth flow for a given provider.
    Only the authenticated athlete (Alumno user) can start their own OAuth flow.
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
        
        # Generate OAuth state with nonce
        try:
            # Build callback URI (allauth handles the actual callback)
            # We're generating state that allauth will validate
            callback_uri = request.build_absolute_uri(reverse("strava_callback"))
            
            oauth_state = generate_oauth_state(
                provider=provider,
                user_id=request.user.id,
                redirect_uri=callback_uri,
            )
        except RuntimeError as e:
            logger.error(
                "oauth.start.nonce_generation_failed",
                extra={
                    "provider": provider,
                    "user_id": request.user.id,
                    "error": str(e),
                },
            )
            return Response(
                {"error": "oauth_setup_failed", "message": "Failed to initialize OAuth flow"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
        # Build OAuth authorization URL
        # For Strava: use allauth's login URL with our custom state
        if provider == "strava":
            oauth_url = request.build_absolute_uri(reverse("strava_login"))
            # Append state as query param (allauth will use it)
            oauth_url = f"{oauth_url}?{urlencode({'state': oauth_state, 'next': f'{FRONTEND_BASE_URL}/athletes/{alumno.id}'})}"
        else:
            # Future providers would have their own URL construction
            return Response(
                {"error": "provider_not_implemented"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
       
        logger.info(
            "oauth.start.initiated",
            extra={
                "provider": provider,
                "user_id": request.user.id,
                "alumno_id": alumno.id,
            },
        )
        
        return Response({
            "oauth_url": oauth_url,
            "provider": provider,
        })


class IntegrationStatusView(APIView):
    """
    GET /api/integrations/status
    
    Get OAuth integration status for all providers for the authenticated athlete.
    Returns connection status, last sync, and error info if applicable.
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
            elif integration_status and integration_status.error_reason:
                # Failed integration with error
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "connected": False,
                    "athlete_id": None,
                    "expires_at": None,
                    "last_sync_at": None,
                    "error_reason": integration_status.error_reason,
                    "last_error_at": integration_status.last_error_at.isoformat() if integration_status.last_error_at else None,
                })
            else:
                # Not connected, no error
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
