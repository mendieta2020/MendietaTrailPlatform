"""
PR11: Provider Connection Status — Read-Only Endpoint

Exposes computed connection status derived from OAuthCredential (PR10).
This endpoint is COMPLEMENTARY to (not a replacement for) the existing
OAuthIntegrationStatus-based endpoints in integration_views.py (Strava).

Scope:
    Non-Strava providers (garmin, coros, suunto, polar, wahoo) that store
    tokens in OAuthCredential. Strava status → GET /api/integrations/status.

Authorization:
    - ATHLETE (IsAthleteUser):  allowed — sees only own alumno (fail-closed).
    - COACH (IsCoachUser only): 403 — use CoachAthleteIntegrationStatusView.
    - Unauthenticated:          401.
    - Staff/admin:              allowed (consistent with repo pattern).

Tenancy guarantee:
    alumno is always resolved via Alumno.objects.get(usuario=request.user).
    No alumno_id accepted in query/body/path (fail-closed by design).
"""
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Alumno
from core.oauth_credentials import compute_connection_status
from core.permissions import IsAthleteUser
from core.providers import SUPPORTED_PROVIDERS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PR12: Provider list is now imported from core.providers (single source of truth).
# Strava status → GET /api/integrations/status (OAuthIntegrationStatus system).
# ---------------------------------------------------------------------------


def _build_connection_payload(provider: str, cs, alumno_id: int) -> dict:
    """
    Build the normalized response dict for a single provider connection.

    Args:
        provider:  Provider string (already lowercased).
        cs:        ConnectionStatus instance from compute_connection_status().
        alumno_id: PK of the resolved Alumno (for reference, not for re-lookup).

    Returns:
        dict — no token values, no raw credential data.
    """
    return {
        "provider": provider,
        "status": cs.status,
        "reason_code": cs.reason_code,
        "expires_at": cs.expires_at.isoformat() if cs.expires_at else None,
        "last_credential_update": cs.updated_at.isoformat() if cs.updated_at else None,
        "alumno_id": alumno_id,
    }


class ProviderConnectionStatusView(APIView):
    """
    GET /api/connections/

    Returns computed connection status for one or all non-Strava providers.

    Query params:
        provider (optional): If provided, return status for that single provider.
                             If omitted, return list for all PR11 providers.

    Response (single provider):
        {
            "provider": "garmin",
            "status": "connected" | "disconnected" | "needs_reauth",
            "reason_code": "" | "no_credential" | "token_expired" | "internal_error",
            "expires_at": null | "<ISO datetime>",
            "last_credential_update": null | "<ISO datetime>",
            "alumno_id": <int>
        }

    Response (all providers):
        {
            "connections": [ { ...same shape... }, ... ],
            "alumno_id": <int>
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # --- Authorization ---
        user = request.user

        # Staff bypass (consistent with repo pattern)
        is_staff = getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)

        # COACH (has students but no perfil_alumno) → 403
        # We detect "coach-only" as: NOT is_staff AND does NOT have perfil_alumno.
        # An athlete always has perfil_alumno.
        is_athlete = hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None) is not None

        if not is_staff and not is_athlete:
            logger.warning(
                "provider_connection_status.forbidden",
                extra={"user_id": user.id, "reason_code": "not_athlete"},
            )
            return Response(
                {"error": "forbidden", "message": "This endpoint is restricted to athletes."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # --- Resolve alumno (tenant-safe) ---
        try:
            if is_staff:
                # Staff: still require perfil_alumno for this endpoint (no alumno_id param accepted)
                alumno = Alumno.objects.get(usuario=user)
            else:
                alumno = Alumno.objects.get(usuario=user)
        except Alumno.DoesNotExist:
            logger.warning(
                "provider_connection_status.athlete_not_found",
                extra={"user_id": user.id},
            )
            return Response(
                {"error": "athlete_not_found", "message": "No athlete profile found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Resolve provider ---
        provider_param = request.query_params.get("provider", "").strip().lower()

        if provider_param:
            # PR12: Validate provider against canonical registry (fail-closed)
            if provider_param not in SUPPORTED_PROVIDERS:
                logger.warning(
                    "provider_connection_status.invalid_provider",
                    extra={"user_id": user.id, "provider": provider_param},
                )
                return Response(
                    {
                        "error": "invalid_provider",
                        "message": f"Provider '{provider_param}' is not supported. "
                                   f"Supported providers: {SUPPORTED_PROVIDERS}",
                        "supported_providers": SUPPORTED_PROVIDERS,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Strava uses OAuthIntegrationStatus — redirect callers
            if provider_param == "strava":
                return Response(
                    {
                        "error": "wrong_endpoint",
                        "message": "Strava status is available at GET /api/integrations/status",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Single-provider response
            cs = compute_connection_status(alumno=alumno, provider=provider_param)
            logger.info(
                "provider_connection_status.single",
                extra={
                    "alumno_id": alumno.pk,
                    "provider": provider_param,
                    "status": cs.status,
                    "reason_code": cs.reason_code,
                },
            )
            return Response(_build_connection_payload(provider_param, cs, alumno.pk))

        # All-providers response: iterate SUPPORTED_PROVIDERS directly
        connections = []
        for prov in SUPPORTED_PROVIDERS:
            cs = compute_connection_status(alumno=alumno, provider=prov)
            connections.append(_build_connection_payload(prov, cs, alumno.pk))

        logger.info(
            "provider_connection_status.all",
            extra={"alumno_id": alumno.pk, "provider_count": len(connections)},
        )
        return Response({"connections": connections, "alumno_id": alumno.pk})
