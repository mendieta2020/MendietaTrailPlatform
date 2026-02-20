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
from .providers import get_provider, list_providers

logger = logging.getLogger(__name__)


def get_available_providers():
    """
    Get list of all registered providers from canonical registry.

    Includes both enabled (active) and disabled (Coming Soon) providers.
    The frontend uses the 'enabled' flag to show "Próximamente" state.

    Returns:
        List of dicts with provider metadata.
    """
    providers = list_providers()
    return [
        {
            "id": provider_obj.provider_id,
            "name": provider_obj.display_name,
            # Use the actual enabled property — NOT hardcoded True
            "enabled": getattr(provider_obj, "enabled", False),
        }
        for provider_id, provider_obj in providers.items()
    ]


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
        """
        Initiate OAuth flow for provider.
        
        Provider-agnostic: uses provider registry to support multiple providers.
        """
        # Get provider from registry
        provider_obj = get_provider(provider)
        if not provider_obj:
            return Response(
                {"error": "unknown_provider", "message": f"Provider '{provider}' not supported"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard: provider registered but not yet enabled (Coming Soon)
        # Return 422 Unprocessable Entity — not a server error, not a bad request.
        # The provider exists but is explicitly disabled until implementation is complete.
        if not getattr(provider_obj, "enabled", False):
            logger.info(
                "oauth.start.provider_disabled",
                extra={
                    "provider": provider,
                    "user_id": request.user.id,
                },
            )
            return Response(
                {
                    "error": "provider_disabled",
                    "message": f"{provider_obj.display_name} integration is not yet available.",
                    "provider": provider,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Validate user has Alumno profile
        try:
            alumno = Alumno.objects.get(usuario=request.user)
        except Alumno.DoesNotExist:
            return Response(
                {"error": "athlete_not_found", "message": "No athlete profile found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Build callback URI (provider-specific pattern)
        callback_uri = self._get_callback_uri(provider)
        
        if not callback_uri:
            logger.error("oauth.start.missing_callback_uri", extra={"provider": provider})
            return Response(
                {"error": "server_misconfigured", "message": "OAuth callback URI not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
        # Provider-specific configuration check
        if not self._validate_provider_config(provider):
            return Response(
                {"error": "provider_not_configured", "message": f"{provider_obj.display_name} integration not configured"},
               status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
        # Generate state with alumno_id (securely signed)
        state = generate_oauth_state(
            provider=provider,
            user_id=request.user.id,
            alumno_id=alumno.id,  # ← Track which alumno is connecting
            redirect_uri=callback_uri,
        )
        
        # Get OAuth URL from provider
        oauth_url = provider_obj.get_oauth_authorize_url(state, callback_uri)
        
        logger.info(
            "oauth.start.success",
            extra={
                "provider": provider,
                "user_id": request.user.id,
                "alumno_id": alumno.id,
                "callback_uri": callback_uri,
            },
        )
        
        return Response({
            "authorization_url": oauth_url,  # New canonical key
            "oauth_url": oauth_url,          # Backward compatibility
            "provider": provider,
        })

    
    def _get_callback_uri(self, provider):
        """Get callback URI for provider (provider-specific settings)."""
        if provider == "strava":
            # Use configured STRAVA_INTEGRATION_CALLBACK_URI
            callback_uri = getattr(settings, 'STRAVA_INTEGRATION_CALLBACK_URI', None)
            
            if not callback_uri:
                # Fallback: construct from PUBLIC_BASE_URL
                public_base = getattr(settings, 'PUBLIC_BASE_URL', 'http://localhost:8000')
                callback_uri = f"{public_base}/api/integrations/strava/callback"
            
            return callback_uri
        
        # For other providers, use generic pattern
        # Example: GARMIN_INTEGRATION_CALLBACK_URI or fallback to PUBLIC_BASE_URL
        public_base = getattr(settings, 'PUBLIC_BASE_URL', 'http://localhost:8000')
        return f"{public_base}/api/integrations/{provider}/callback"
    
    def _validate_provider_config(self, provider):
        """Validate provider has required configuration (client ID, secret, etc)."""
        if provider == "strava":
            client_id = getattr(settings, 'STRAVA_CLIENT_ID', None)
            if not client_id:
                return False
        
        # For other providers, add config checks:
        # elif provider == "garmin":
        #     return bool(getattr(settings, 'GARMIN_CLIENT_ID', None))
        
        return True


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
            
            if integration_status:
                # Use explicit status if available, fallback to computed
                status_value = integration_status.status
                if not status_value or status_value == OAuthIntegrationStatus.Status.DISCONNECTED:
                     # Legacy fallback check
                     if integration_status.connected:
                         status_value = "connected"
                     elif integration_status.error_reason:
                         status_value = "error"
                     else:
                         status_value = "unlinked"
                
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "status": status_value,
                    "connected": integration_status.connected,
                    "athlete_id": integration_status.athlete_id,
                    "expires_at": integration_status.expires_at.isoformat() if integration_status.expires_at else None,
                    "last_sync_at": integration_status.last_sync_at.isoformat() if integration_status.last_sync_at else None,
                    "error_reason": integration_status.error_reason,
                    "last_error": integration_status.error_message,
                     "last_error_at": integration_status.last_error_at.isoformat() if integration_status.last_error_at else None,
                })
            else:
                # Not connected, no attempt yet
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "enabled": provider_data["enabled"],
                    "status": "unlinked",
                    "connected": False,
                    "athlete_id": None,
                    "expires_at": None,
                    "last_sync_at": None,
                    "error_reason": None,
                    "last_error": None,
                })
        
        return Response({
            "integrations": integrations,
            "athlete_id": alumno.id,
        })


class ProviderStatusView(APIView):
    """
    GET /api/integrations/{provider}/status
    
    Returns normalized integration status for a specific provider.
    
    Response schema:
    {
        "provider": str,
        "status": "connected" | "unlinked" | "error",
        "external_user_id": str,
        "athlete_id": str (alias for external_user_id),
        "linked_at": str (ISO datetime) | null,
        "last_sync_at": str (ISO datetime) | null,
        "error_reason": str (if status="error")
    }
    
    Multi-tenant safe: returns only current athlete's status.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, provider):
        """Get integration status for specific provider"""
        # Get athlete profile
        try:
            alumno = Alumno.objects.get(usuario=request.user)
        except Alumno.DoesNotExist:
            return Response(
                {"error": "athlete_not_found", "message": "No athlete profile found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Fetch integration status for this provider (or None if not linked)
        try:
            integration = OAuthIntegrationStatus.objects.get(
                alumno=alumno,
                provider=provider,
            )
            
            # Use explicit status if available, fallback to computed
            status_value = integration.status
            if not status_value or status_value == OAuthIntegrationStatus.Status.DISCONNECTED:
                 # Legacy fallback check
                 if integration.connected:
                     status_value = "connected"
                 elif integration.error_reason:
                     status_value = "error"
                 else:
                     status_value = "unlinked"
            
            return Response({
                "provider": provider,
                "status": status_value,
                "connected": integration.connected,
                "external_user_id": integration.athlete_id or "",
                "athlete_id": integration.athlete_id or "",  # Alias for backwards compat
                "linked_at": integration.created_at.isoformat() if integration.created_at else None,
                "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
                "error_reason": integration.error_reason or "",
                "last_error": integration.error_message or "",
            })
            
        except OAuthIntegrationStatus.DoesNotExist:
            # Not linked yet - return unlinked status
            return Response({
                "provider": provider,
                "status": "unlinked",
                "connected": False,
                "external_user_id": "",
                "athlete_id": "",
                "linked_at": None,
                "last_sync_at": None,
                "error_reason": "",
                "last_error": "",
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
            
            if integration_status:
                status_value = integration_status.status
                if not status_value or status_value == OAuthIntegrationStatus.Status.DISCONNECTED:
                     if integration_status.connected:
                         status_value = "connected"
                     elif integration_status.error_reason:
                         status_value = "error"
                     else:
                         status_value = "unlinked"
                
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "status": status_value,
                    "connected": integration_status.connected,
                    "athlete_id": integration_status.athlete_id,
                    "last_sync_at": integration_status.last_sync_at.isoformat() if integration_status.last_sync_at else None,
                    "last_error": integration_status.error_message,
                    "error_reason": integration_status.error_reason,
                })
            else:
                # Not connected or failed
                integrations.append({
                    "provider": provider_id,
                    "name": provider_data["name"],
                    "status": "unlinked",
                    "connected": False,
                    "athlete_id": None,
                    "last_sync_at": None,
                    "last_error": None,
                    "error_reason": None,
                })
        
        return Response({
            "integrations": integrations,
            "athlete_id": alumno.id,
            "athlete_name": alumno.nombre,
        })
