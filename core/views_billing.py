import json
import logging
import requests as http_requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

from core.billing import require_plan  # plan gate decorator

logger = logging.getLogger(__name__)


class BillingOrgMixin:
    """
    PR-150: Resolves the authenticated user's organization from Membership.

    Replaces the broken `getattr(request, "auth_organization", None)` pattern
    which was never populated by any middleware in production.
    Owner and admin roles can access billing features.

    PR-149: Fixed non-deterministic org selection for multi-org users.
    If the user holds coaching roles in more than one org, the caller must
    supply ?org_id=<pk> (GET) or {"org_id": <pk>} (POST body) to disambiguate.
    Returns None (→ 403) if the org cannot be resolved unambiguously.
    """

    def get_org(self, request):
        from core.models import Membership
        try:
            memberships = list(
                Membership.objects.select_related("organization").filter(
                    user=request.user,
                    is_active=True,
                    role__in=["owner", "admin", "coach"],
                )
            )
            if not memberships:
                return None

            # Support both DRF Request (query_params) and raw Django WSGIRequest (GET)
            query_params = getattr(request, "query_params", request.GET)
            raw_org_id = query_params.get("org_id") or (
                request.data.get("org_id") if hasattr(request, "data") else None
            )

            if raw_org_id is not None:
                # Explicit org_id supplied: validate it against the user's memberships
                try:
                    org_id = int(raw_org_id)
                except (TypeError, ValueError):
                    return None
                matched = [m for m in memberships if m.organization_id == org_id]
                if len(matched) != 1:
                    return None
                m = matched[0]
            elif len(memberships) == 1:
                # Single membership and no org_id required — safe auto-resolution
                m = memberships[0]
            else:
                # Multi-org user without org_id: deny to avoid non-deterministic selection
                logger.warning(
                    "billing.get_org.ambiguous",
                    extra={
                        "event_name": "billing.get_org.ambiguous",
                        "user_id": request.user.pk,
                        "org_count": len(memberships),
                        "outcome": "denied",
                    },
                )
                return None

            # Also set on request for backward compat with require_plan
            request.auth_organization = m.organization
            return m.organization
        except Exception:
            pass
        return None


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    from integrations.mercadopago.webhook import process_subscription_webhook  # lazy — Law 4
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("mp.webhook.invalid_json")
        return HttpResponse(status=400)

    process_subscription_webhook(payload)
    return HttpResponse(status=200)


class BillingStatusView(BillingOrgMixin, APIView):
    """
    GET /api/billing/status/
    Returns the subscription state for the request's organization.
    Accessible by coach and owner.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.serializers_billing import BillingStatusSerializer
        from core.models import OrganizationSubscription, OrgOAuthCredential
        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            subscription = OrganizationSubscription.objects.get(organization=org)
        except OrganizationSubscription.DoesNotExist:
            # Return a minimal status instead of 404 — org exists but no B2B subscription
            mp_connected = OrgOAuthCredential.objects.filter(
                organization=org, provider="mercadopago",
            ).exists()
            return Response({
                "plan": "free",
                "plan_display": "Free",
                "is_active": True,
                "mp_connected": mp_connected,
            })
        serializer = BillingStatusSerializer(subscription)
        data = serializer.data
        # Add MP connection status
        data["mp_connected"] = OrgOAuthCredential.objects.filter(
            organization=org, provider="mercadopago",
        ).exists()
        return Response(data)


class BillingSubscribeView(BillingOrgMixin, APIView):
    """
    POST /api/billing/subscribe/
    Body: {"plan_id": <SubscriptionPlan pk>}
    Creates a MercadoPago subscription and returns init_point (checkout URL).
    Only coaches/owners. Plan must have mp_plan_id configured.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import SubscriptionPlan, OrganizationSubscription
        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response(
                {"detail": "plan_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan = SubscriptionPlan.objects.get(pk=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {"detail": "Plan not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not plan.mp_plan_id:
            return Response(
                {"detail": "Plan not yet configured in MercadoPago."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from integrations.mercadopago.subscriptions import create_subscription  # lazy — Law 4
            mp_data = create_subscription(
                mp_plan_id=plan.mp_plan_id,
                payer_email=request.user.email,
                reason=f"Quantoryn {plan.name} — {org.name}",
            )
        except Exception as exc:
            logger.error(
                "billing.subscribe.mp_error",
                extra={
                    "organization_id": org.pk,
                    "plan_id": plan.pk,
                    "error": str(exc),
                    "outcome": "error",
                },
            )
            return Response(
                {"detail": "Error creating subscription in MercadoPago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        subscription, _ = OrganizationSubscription.objects.get_or_create(
            organization=org
        )
        subscription.mp_preapproval_id = mp_data.get("id")
        subscription.plan = plan.plan_tier
        subscription.save(update_fields=["mp_preapproval_id", "plan", "updated_at"])

        logger.info(
            "billing.subscribe.created",
            extra={
                "organization_id": org.pk,
                "plan_tier": plan.plan_tier,
                "mp_preapproval_id": mp_data.get("id"),
                "outcome": "created",
            },
        )

        return Response(
            {
                "checkout_url": mp_data.get("init_point"),
                "mp_preapproval_id": mp_data.get("id"),
                "plan": plan.plan_tier,
            },
            status=status.HTTP_201_CREATED,
        )


class BillingCancelView(BillingOrgMixin, APIView):
    """
    POST /api/billing/cancel/
    Cancels the organization's active MP subscription and marks it as inactive locally.
    Only coaches/owners.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import OrganizationSubscription
        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            subscription = OrganizationSubscription.objects.get(organization=org)
        except OrganizationSubscription.DoesNotExist:
            return Response(
                {"detail": "No active subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not subscription.mp_preapproval_id:
            return Response(
                {"detail": "No MercadoPago subscription to cancel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from integrations.mercadopago.subscriptions import cancel_subscription  # lazy — Law 4
            cancel_subscription(subscription.mp_preapproval_id)
        except Exception as exc:
            logger.error(
                "billing.cancel.mp_error",
                extra={
                    "organization_id": org.pk,
                    "mp_preapproval_id": subscription.mp_preapproval_id,
                    "error": str(exc),
                    "outcome": "error",
                },
            )
            return Response(
                {"detail": "Error cancelling subscription in MercadoPago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        subscription.is_active = False
        subscription.plan = OrganizationSubscription.Plan.FREE
        subscription.save(update_fields=["is_active", "plan", "updated_at"])

        logger.info(
            "billing.cancel.completed",
            extra={
                "organization_id": org.pk,
                "outcome": "cancelled",
            },
        )

        return Response({"detail": "Subscription cancelled."})


# ==============================================================================
# PR-134: Coach MP OAuth Connect / Callback / Disconnect
# ==============================================================================


class MPConnectView(BillingOrgMixin, APIView):
    """
    GET /api/billing/mp/connect/
    Returns the MercadoPago authorization URL. The frontend redirects the coach
    there to grant Quantoryn access to their MP account.
    Requires: authenticated user (owner/admin/coach).
    PR-150: Removed require_plan("pro") — MP connect must be available before plan creation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from integrations.mercadopago.oauth import mp_get_authorization_url  # lazy — Law 4

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        authorization_url = mp_get_authorization_url(org.pk)
        logger.info(
            "mp.oauth.connect.initiated",
            extra={"organization_id": org.pk, "outcome": "url_generated"},
        )
        return Response({"authorization_url": authorization_url})


class MPCallbackView(APIView):
    """
    GET /api/billing/mp/callback/
    External callback from MercadoPago after the coach authorizes.
    No auth required — this URL is called by MP's servers/browser redirect.

    Flow:
        1. Validate state (org_id) maps to a real Organization.
        2. Exchange code for MP tokens.
        3. Upsert OrgOAuthCredential(org, provider="mercadopago").
        4. Redirect browser to frontend billing settings page.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # Skip session/JWT — public callback

    def get(self, request):
        from integrations.mercadopago.oauth import mp_exchange_code  # lazy — Law 4
        from core.models import Membership, OrgOAuthCredential, Organization
        from django.conf import settings as django_settings
        from django.shortcuts import redirect as django_redirect

        state = request.GET.get("state", "")
        code = request.GET.get("code", "")

        if not state:
            return Response(
                {"detail": "Missing state parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve org from state — minimal anti-CSRF
        try:
            org = Organization.objects.get(pk=int(state))
        except (Organization.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Invalid state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify org has at least one member (guards against forged state values)
        if not Membership.objects.filter(organization=org).exists():
            return Response(
                {"detail": "Invalid state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not code:
            logger.warning(
                "mp.oauth.callback.missing_code",
                extra={"organization_id": org.pk, "outcome": "error"},
            )
            return Response(
                {"detail": "Missing code parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_data = mp_exchange_code(code)
        except ValueError as exc:
            logger.error(
                "mp.oauth.callback.exchange_error",
                extra={"organization_id": org.pk, "outcome": "error", "error": str(exc)},
            )
            return Response(
                {"detail": "Error exchanging code with MercadoPago."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        provider_user_id = str(token_data.get("user_id", ""))

        cred, created = OrgOAuthCredential.objects.get_or_create(
            organization=org,
            provider="mercadopago",
            defaults={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "provider_user_id": provider_user_id,
            },
        )
        if not created:
            cred.access_token = access_token
            cred.refresh_token = refresh_token
            cred.provider_user_id = provider_user_id
            cred.save(update_fields=["access_token", "refresh_token", "provider_user_id", "updated_at"])

        logger.info(
            "mp.oauth.callback.success",
            extra={
                "organization_id": org.pk,
                "created": created,
                "outcome": "connected",
            },
        )

        frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")
        return django_redirect(f"{frontend_url}/finance?mp_connected=true")


class MPDisconnectView(BillingOrgMixin, APIView):
    """
    DELETE /api/billing/mp/disconnect/
    Removes the coach's MP OAuth credential for this organization.
    Requires: authenticated user, pro plan.
    """

    permission_classes = [IsAuthenticated]

    @require_plan("pro")
    def delete(self, request):
        from core.models import OrgOAuthCredential

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        OrgOAuthCredential.objects.filter(organization=org, provider="mercadopago").delete()
        logger.info(
            "mp.oauth.disconnect",
            extra={"organization_id": org.pk, "outcome": "disconnected"},
        )
        return Response({"disconnected": True})


# ==============================================================================
# PR-135: AthleteInvitation views
# ==============================================================================


class InvitationCreateView(BillingOrgMixin, APIView):
    """
    GET  /api/billing/invitations/ — List invitations for the org (owner/admin).
    POST /api/billing/invitations/ — Create invitation link (owner/admin + pro plan).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import AthleteInvitation, Membership
        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)
        try:
            membership = Membership.objects.get(user=request.user, organization=org)
        except Membership.DoesNotExist:
            return Response({"detail": "Sin acceso."}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in ("owner", "admin"):
            return Response({"detail": "Solo owner o admin."}, status=status.HTTP_403_FORBIDDEN)

        invitations = (
            AthleteInvitation.objects
            .filter(organization=org)
            .select_related("coach_plan")
            .order_by("-created_at")
        )
        data = [
            {
                "id": inv.pk,
                "token": str(inv.token),
                "email": inv.email,
                "status": inv.status,
                "coach_plan_id": inv.coach_plan_id,
                "coach_plan_name": inv.coach_plan.name if inv.coach_plan else "Sin plan (atleta elige)",
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invitations
        ]
        return Response(data)

    @require_plan("pro")
    def post(self, request):
        from core.models import AthleteInvitation
        from core.serializers_billing import AthleteInvitationCreateSerializer
        from django.utils import timezone
        from datetime import timedelta
        from django.conf import settings as django_settings

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from core.models import Membership
        try:
            membership = Membership.objects.get(user=request.user, organization=org)
        except Membership.DoesNotExist:
            return Response(
                {"detail": "No tienes membresía en esta organización."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if membership.role not in ("owner", "admin"):
            return Response(
                {"detail": "Solo owner o admin pueden enviar invitaciones."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AthleteInvitationCreateSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        coach_plan = serializer.validated_data["coach_plan"]
        email = serializer.validated_data["email"]
        now = timezone.now()
        invitation = AthleteInvitation.objects.create(
            organization=org,
            coach_plan=coach_plan,
            email=email,
            expires_at=now + timedelta(days=30),
        )

        frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")
        invite_url = f"{frontend_url}/invite/{invitation.token}"

        logger.info(
            "invitation_created",
            extra={
                "organization_id": org.pk,
                "invitation_id": invitation.pk,
                "coach_plan_id": coach_plan.pk,
                "outcome": "created",
            },
        )

        return Response(
            {"token": str(invitation.token), "invite_url": invite_url},
            status=status.HTTP_201_CREATED,
        )


class InvitationDetailView(APIView):
    """
    GET /api/billing/invitations/<token>/
    Public — used by athlete to view invitation details before accepting.
    Returns no sensitive data (no token, email, preapproval_id).
    PR-138: revised response format.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        from core.models import AthleteInvitation

        try:
            invitation = AthleteInvitation.objects.select_related(
                "coach_plan", "organization"
            ).get(token=token)
        except AthleteInvitation.DoesNotExist:
            return Response({"detail": "Invitación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if invitation.status == AthleteInvitation.Status.PENDING and invitation.is_expired():
            invitation.status = AthleteInvitation.Status.EXPIRED
            invitation.save(update_fields=["status"])

        if invitation.status == AthleteInvitation.Status.ACCEPTED:
            return Response({"status": "already_accepted"})

        if invitation.status == AthleteInvitation.Status.EXPIRED:
            return Response({"status": "expired"})

        data = {
            "status": "pending",
            "organization_name": invitation.organization.name,
            "currency": "ARS",
            "expires_at": invitation.expires_at.isoformat(),
        }

        if invitation.coach_plan:
            # Pre-assigned plan (backward compatible)
            data["plan_name"] = invitation.coach_plan.name
            data["price"] = str(invitation.coach_plan.price_ars)
        else:
            # No plan pre-assigned — return all active plans for athlete selection
            from core.models import CoachPricingPlan
            plans = CoachPricingPlan.objects.filter(
                organization=invitation.organization, is_active=True,
            ).order_by("price_ars")
            data["plans"] = [
                {"id": p.pk, "name": p.name, "price": str(p.price_ars)}
                for p in plans
            ]

        return Response(data)


class InvitationAcceptView(APIView):
    """
    POST /api/billing/invitations/<token>/accept/
    Authenticated athlete accepts → creates Membership + MP preapproval.
    PR-138: requires authentication; creates Membership; returns redirect_url.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        from core.models import AthleteInvitation, OrgOAuthCredential, AthleteSubscription, Membership
        from django.utils import timezone
        from integrations.mercadopago.subscriptions import create_coach_athlete_preapproval  # lazy — Law 4
        from django.conf import settings as django_settings

        try:
            invitation = AthleteInvitation.objects.select_related(
                "coach_plan", "organization"
            ).get(token=token)
        except AthleteInvitation.DoesNotExist:
            return Response({"detail": "Invitación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Check expiry first (regardless of status)
        if invitation.status == AthleteInvitation.Status.PENDING and invitation.is_expired():
            invitation.status = AthleteInvitation.Status.EXPIRED
            invitation.save(update_fields=["status"])

        if invitation.status == AthleteInvitation.Status.EXPIRED:
            return Response({"error": "invitation_expired"}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent: if already accepted, check if this user is already a member
        if invitation.status == AthleteInvitation.Status.ACCEPTED:
            already_member = Membership.objects.filter(
                user=request.user,
                organization=invitation.organization,
                role="athlete",
            ).exists()
            if already_member:
                return Response({"redirect_url": "/dashboard", "already_member": True})

        if invitation.status not in (
            AthleteInvitation.Status.PENDING,
            AthleteInvitation.Status.ACCEPTED,
        ):
            return Response({"detail": "Invitación no disponible."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure MP credential exists before creating membership
        try:
            cred = OrgOAuthCredential.objects.get(
                organization=invitation.coach_plan.organization,
                provider="mercadopago",
            )
        except OrgOAuthCredential.DoesNotExist:
            return Response(
                {"detail": "El coach no tiene MercadoPago conectado."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        if not invitation.coach_plan.mp_plan_id:
            return Response(
                {"detail": "El plan del coach no está configurado en MercadoPago."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")

        try:
            mp_data = create_coach_athlete_preapproval(
                access_token=cred.access_token,  # Law 6: never logged
                mp_plan_id=invitation.coach_plan.mp_plan_id,
                payer_email=invitation.email,
                reason=f"Quantoryn {invitation.coach_plan.name} — {invitation.organization.name}",
                back_url=f"{frontend_url}/invite/{invitation.token}/callback",
            )
        except Exception as exc:
            logger.error(
                "invitation_accept.mp_error",
                extra={
                    "organization_id": invitation.organization_id,
                    "invitation_id": invitation.pk,
                    "error": str(exc),
                    "outcome": "error",
                },
            )
            return Response(
                {"detail": "Error al crear el preapproval en MercadoPago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        preapproval_id = mp_data.get("id")
        init_point = mp_data.get("init_point")

        # Create Membership idempotently (Law 5)
        Membership.objects.get_or_create(
            user=request.user,
            organization=invitation.organization,
            defaults={"role": "athlete"},
        )

        # Mark invitation accepted
        invitation.mp_preapproval_id = preapproval_id
        invitation.status = AthleteInvitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["mp_preapproval_id", "status", "accepted_at"])

        # Create AthleteSubscription if the user has an Athlete profile
        from core.models import Athlete
        athlete = Athlete.objects.filter(
            user=request.user,
            organization=invitation.organization,
        ).first()
        if athlete:
            AthleteSubscription.objects.get_or_create(
                athlete=athlete,
                coach_plan=invitation.coach_plan,
                defaults={
                    "organization": invitation.organization,
                    "status": AthleteSubscription.Status.PENDING,
                    "mp_preapproval_id": preapproval_id,
                },
            )

        logger.info(
            "invitation_accepted",
            extra={
                "organization_id": invitation.organization_id,
                "invitation_id": invitation.pk,
                "user_id": request.user.pk,
                "outcome": "success",
            },
        )

        return Response({"redirect_url": init_point}, status=status.HTTP_200_OK)


class InvitationRejectView(APIView):
    """
    POST /api/billing/invitations/<token>/reject/
    Athlete declines the invitation.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, token):
        from core.models import AthleteInvitation

        try:
            invitation = AthleteInvitation.objects.get(token=token)
        except AthleteInvitation.DoesNotExist:
            return Response({"detail": "Invitación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if invitation.status != AthleteInvitation.Status.PENDING:
            return Response(
                {"detail": "Invitación no disponible."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation.status = AthleteInvitation.Status.REJECTED
        invitation.save(update_fields=["status"])

        logger.info(
            "invitation_rejected",
            extra={
                "organization_id": invitation.organization_id,
                "invitation_id": invitation.pk,
                "outcome": "rejected",
            },
        )

        return Response({"status": "rejected"})


# ==============================================================================
# PR-136: AthleteSubscription webhook handler (coach→athlete payment sync)
# ==============================================================================


@method_decorator(csrf_exempt, name="dispatch")
class AthleteSubscriptionWebhookView(View):
    """
    POST /api/webhooks/mercadopago/athlete/
    Webhook endpoint para eventos de pago de atletas (coach→atleta).
    Separado del webhook B2B de Quantoryn (webhooks/mercadopago/).
    """

    def post(self, request):
        from integrations.mercadopago.webhook_security import verify_mp_signature  # lazy — Law 4

        if not verify_mp_signature(request):
            logger.warning(
                "mp.athlete_webhook.signature_rejected",
                extra={
                    "event_name": "mp.athlete_webhook.signature_rejected",
                    "remote_addr": request.META.get("REMOTE_ADDR", ""),
                    "outcome": "rejected",
                },
            )
            return JsonResponse({"detail": "Invalid signature"}, status=401)

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("mp.athlete_webhook.invalid_json")
            return JsonResponse({"error": "invalid json"}, status=400)

        from integrations.mercadopago.athlete_webhook import (  # lazy — Law 4
            process_athlete_subscription_webhook,
        )

        result = process_athlete_subscription_webhook(payload)
        return JsonResponse(result, status=200)


class InvitationResendView(BillingOrgMixin, APIView):
    """
    POST /api/billing/invitations/<token>/resend/
    Coach regenerates token and extends expiry.
    Requires: authenticated, pro plan.
    """
    permission_classes = [IsAuthenticated]

    @require_plan("pro")
    def post(self, request, token):
        import uuid as _uuid
        from core.models import AthleteInvitation
        from django.utils import timezone
        from datetime import timedelta
        from django.conf import settings as django_settings

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from core.models import Membership
        try:
            membership = Membership.objects.get(user=request.user, organization=org)
        except Membership.DoesNotExist:
            return Response(
                {"detail": "No tienes membresía en esta organización."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if membership.role not in ("owner", "admin"):
            return Response(
                {"detail": "Solo owner o admin pueden reenviar invitaciones."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            invitation = AthleteInvitation.objects.get(token=token)
        except AthleteInvitation.DoesNotExist:
            return Response({"detail": "Invitación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if invitation.organization_id != org.pk:
            return Response({"detail": "No tienes permiso para esta invitación."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        invitation.token = _uuid.uuid4()
        invitation.expires_at = now + timedelta(days=30)
        invitation.status = AthleteInvitation.Status.PENDING
        invitation.save(update_fields=["token", "expires_at", "status"])

        frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")
        invite_url = f"{frontend_url}/invite/{invitation.token}"

        logger.info(
            "invitation_resent",
            extra={
                "organization_id": org.pk,
                "email": invitation.email,
                "outcome": "resent",
            },
        )

        return Response({"token": str(invitation.token), "invite_url": invite_url})


# ==============================================================================
# PR-137: Billing UI — Plans, AthleteSubscriptions
# ==============================================================================


class CoachPricingPlanListCreateView(BillingOrgMixin, APIView):
    """
    GET  /api/billing/plans/ — List CoachPricingPlans for the org.
    POST /api/billing/plans/ — Create a new plan (owner/admin + pro).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import CoachPricingPlan
        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)
        plans = CoachPricingPlan.objects.filter(organization=org, is_active=True).order_by("price_ars")
        data = [
            {
                "id": p.pk,
                "name": p.name,
                "description": p.description,
                "price_ars": str(p.price_ars),
                "is_active": p.is_active,
                "mp_plan_id": p.mp_plan_id,
                "created_at": p.created_at.isoformat(),
            }
            for p in plans
        ]
        return Response(data)

    def post(self, request):
        from core.models import CoachPricingPlan
        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get("name", "").strip()
        price_ars = request.data.get("price_ars")
        description = request.data.get("description", "")
        if not name:
            return Response({"detail": "name es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if price_ars is None:
            return Response({"detail": "price_ars es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        plan = CoachPricingPlan.objects.create(
            organization=org,
            name=name,
            price_ars=price_ars,
            description=description,
        )
        logger.info(
            "coach_pricing_plan.created",
            extra={"organization_id": org.pk, "plan_id": plan.pk, "outcome": "created"},
        )
        return Response(
            {
                "id": plan.pk,
                "name": plan.name,
                "description": plan.description,
                "price_ars": str(plan.price_ars),
                "is_active": plan.is_active,
                "mp_plan_id": plan.mp_plan_id,
            },
            status=status.HTTP_201_CREATED,
        )


class CoachPricingPlanDetailView(BillingOrgMixin, APIView):
    """
    PR-151: PUT/PATCH/DELETE /api/billing/plans/<pk>/
    Edit or soft-delete a pricing plan.
    """
    permission_classes = [IsAuthenticated]

    def _get_plan(self, request, pk):
        from core.models import CoachPricingPlan
        org = self.get_org(request)
        if org is None:
            return None, None, Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            plan = CoachPricingPlan.objects.get(pk=pk, organization=org)
        except CoachPricingPlan.DoesNotExist:
            return None, None, Response(
                {"detail": "Plan no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return org, plan, None

    def put(self, request, pk):
        org, plan, error = self._get_plan(request, pk)
        if error:
            return error

        name = request.data.get("name", plan.name).strip()
        price_ars = request.data.get("price_ars", plan.price_ars)
        description = request.data.get("description", plan.description)
        is_active = request.data.get("is_active", plan.is_active)

        plan.name = name
        plan.price_ars = price_ars
        plan.description = description
        plan.is_active = is_active
        plan.save(update_fields=["name", "price_ars", "description", "is_active", "updated_at"])

        logger.info(
            "coach_plan.updated",
            extra={"organization_id": org.pk, "plan_id": plan.pk, "outcome": "updated"},
        )

        return Response({
            "id": plan.pk,
            "name": plan.name,
            "description": plan.description,
            "price_ars": str(plan.price_ars),
            "is_active": plan.is_active,
        })

    patch = put  # PATCH behaves same as PUT (partial update)

    def delete(self, request, pk):
        org, plan, error = self._get_plan(request, pk)
        if error:
            return error

        from core.models import AthleteSubscription
        active_count = AthleteSubscription.objects.filter(
            coach_plan=plan,
            status=AthleteSubscription.Status.ACTIVE,
        ).count()
        if active_count > 0:
            return Response(
                {"detail": f"No se puede eliminar: tiene {active_count} atleta(s) suscripto(s). Desactivalo en vez de eliminar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Soft-delete: deactivate instead of removing (preserves subscription references)
        plan.is_active = False
        plan.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "coach_plan.deactivated",
            extra={"organization_id": org.pk, "plan_id": plan.pk, "outcome": "deactivated"},
        )

        return Response({"id": plan.pk, "deactivated": True})


class AthleteSubscriptionListView(BillingOrgMixin, APIView):
    """
    GET /api/billing/athlete-subscriptions/
    List AthleteSubscriptions for the org with athlete data.
    Requires: authenticated. Owner/admin see all; coach sees own athletes only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import AthleteSubscription, Membership
        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)
        try:
            membership = Membership.objects.get(user=request.user, organization=org)
        except Membership.DoesNotExist:
            return Response({"detail": "Sin acceso."}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in ("owner", "admin"):
            return Response({"detail": "Solo owner o admin."}, status=status.HTTP_403_FORBIDDEN)

        subscriptions = (
            AthleteSubscription.objects
            .filter(organization=org)
            .select_related("athlete__user", "athlete", "coach_plan")
            .order_by("status", "-created_at")
        )
        data = [
            {
                "id": sub.pk,
                "athlete_id": sub.athlete_id,
                "athlete_first_name": sub.athlete.user.first_name,
                "athlete_last_name": sub.athlete.user.last_name,
                "athlete_email": sub.athlete.user.email,
                "athlete_phone": sub.athlete.phone_number,
                "coach_plan_id": sub.coach_plan_id,
                "coach_plan_name": sub.coach_plan.name,
                "price_ars": str(sub.coach_plan.price_ars),
                "status": sub.status,
                "mp_preapproval_id": sub.mp_preapproval_id,
                "last_payment_at": sub.last_payment_at.isoformat() if sub.last_payment_at else None,
                "next_payment_at": sub.next_payment_at.isoformat() if sub.next_payment_at else None,
                "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
                "created_at": sub.created_at.isoformat(),
            }
            for sub in subscriptions
        ]
        return Response(data)


class AthleteSubscriptionActivateView(BillingOrgMixin, APIView):
    """
    POST /api/billing/athlete-subscriptions/<pk>/activate/
    Manual activation (cash/transfer, no MP). Owner/admin only + pro plan.
    """
    permission_classes = [IsAuthenticated]

    @require_plan("pro")
    def post(self, request, pk):
        from core.models import AthleteSubscription, Membership, OrgOAuthCredential, InternalMessage
        from django.utils import timezone
        from datetime import timedelta

        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)
        try:
            membership = Membership.objects.get(user=request.user, organization=org)
        except Membership.DoesNotExist:
            return Response({"detail": "Sin acceso."}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in ("owner", "admin"):
            return Response({"detail": "Solo owner o admin pueden activar manualmente."}, status=status.HTTP_403_FORBIDDEN)

        try:
            sub = AthleteSubscription.objects.select_related("athlete__user", "coach_plan").get(pk=pk, organization=org)
        except AthleteSubscription.DoesNotExist:
            return Response({"detail": "Suscripción no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status == AthleteSubscription.Status.ACTIVE:
            return Response({"detail": "La suscripción ya está activa."}, status=status.HTTP_400_BAD_REQUEST)

        mp_linked = False
        plan_mp_id = sub.coach_plan.mp_plan_id if sub.coach_plan else None
        cred = OrgOAuthCredential.objects.filter(organization=org, provider="mercadopago").first()

        if cred and plan_mp_id:
            try:
                from integrations.mercadopago.subscriptions import search_preapprovals

                already_assigned = set(
                    AthleteSubscription.objects.filter(
                        organization=org,
                        mp_preapproval_id__isnull=False,
                    ).exclude(pk=sub.pk).values_list("mp_preapproval_id", flat=True)
                )

                raw_results = search_preapprovals(cred.access_token, plan_mp_id, status="authorized")
                available = [r for r in raw_results if r.get("id") not in already_assigned]

                if available:
                    best = max(available, key=lambda r: r.get("date_created") or "")
                    preapproval_id = best.get("id")
                    payer_id = str(best.get("payer_id") or "") or None

                    sub.mp_preapproval_id = preapproval_id
                    sub.mp_payer_id = payer_id
                    sub.save(update_fields=["mp_preapproval_id", "mp_payer_id", "updated_at"])

                    from integrations.mercadopago.athlete_webhook import _apply_status_transition
                    _apply_status_transition(sub, best.get("status"), preapproval_id)
                    # _apply_status_transition sets last_payment_at, next_payment_at, notifies owner
                    mp_linked = True

                    logger.info(
                        "athlete_subscription.activated_with_mp",
                        extra={
                            "event_name": "athlete_subscription.activated_with_mp",
                            "organization_id": org.pk,
                            "subscription_id": sub.pk,
                            "preapproval_id": preapproval_id,
                            "activated_by": request.user.pk,
                            "outcome": "activated",
                        },
                    )
            except Exception as exc:
                logger.warning(
                    "athlete_subscription.activate_mp_search_failed",
                    extra={
                        "event_name": "athlete_subscription.activate_mp_search_failed",
                        "organization_id": org.pk,
                        "subscription_id": sub.pk,
                        "error": str(exc),
                    },
                )

        if not mp_linked:
            now = timezone.now()
            sub.status = AthleteSubscription.Status.ACTIVE
            sub.last_payment_at = now
            sub.next_payment_at = now + timedelta(days=30)
            sub.save(update_fields=["status", "last_payment_at", "next_payment_at", "updated_at"])

            from integrations.mercadopago.athlete_webhook import _notify_owner_payment_received
            _notify_owner_payment_received(sub)

            logger.info(
                "athlete_manual_activation",
                extra={
                    "organization_id": org.pk,
                    "subscription_id": sub.pk,
                    "athlete_id": sub.athlete_id,
                    "activated_by": request.user.pk,
                    "outcome": "activated",
                },
            )

        InternalMessage.objects.create(
            organization=org,
            sender=request.user,
            recipient=sub.athlete.user,
            content=f"Tu suscripción al plan {sub.coach_plan.name if sub.coach_plan else ''} fue activada.",
            alert_type="subscription_activated",
        )

        return Response({"id": sub.pk, "status": sub.status, "mp_linked": mp_linked})


# ==============================================================================
# PR-150: Universal invite link + Athlete subscription self-service
# ==============================================================================


class InviteLinkView(BillingOrgMixin, APIView):
    """
    GET /api/billing/invite-link/
    Returns (or creates) the organization's universal invite link.
    Owner/admin/coach only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import OrganizationInviteLink
        from django.conf import settings as django_settings

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        link, created = OrganizationInviteLink.objects.get_or_create(
            organization=org,
        )

        frontend_url = getattr(
            django_settings, "FRONTEND_BASE_URL",
            getattr(django_settings, "FRONTEND_URL", "http://localhost:5173"),
        )

        return Response({
            "slug": link.slug,
            "url": f"{frontend_url}/join/{link.slug}",
            "is_active": link.is_active,
        })


class InviteLinkRegenerateView(BillingOrgMixin, APIView):
    """
    POST /api/billing/invite-link/regenerate/
    Regenerates the slug (old link becomes invalid).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import uuid as _uuid
        from core.models import OrganizationInviteLink
        from django.conf import settings as django_settings

        org = self.get_org(request)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )

        link, _ = OrganizationInviteLink.objects.get_or_create(
            organization=org,
        )
        link.slug = _uuid.uuid4().hex[:12]
        link.save(update_fields=["slug", "updated_at"])

        frontend_url = getattr(
            django_settings, "FRONTEND_BASE_URL",
            getattr(django_settings, "FRONTEND_URL", "http://localhost:5173"),
        )

        logger.info(
            "invite_link.regenerated",
            extra={"organization_id": org.pk, "outcome": "regenerated"},
        )

        return Response({
            "slug": link.slug,
            "url": f"{frontend_url}/join/{link.slug}",
            "is_active": link.is_active,
        })


class JoinDetailView(APIView):
    """
    GET /api/billing/join/<slug>/
    Public — returns org name + active plans for the universal invite link.
    Used by JoinPage.jsx to show plan selector.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        from core.models import OrganizationInviteLink, CoachPricingPlan

        try:
            link = OrganizationInviteLink.objects.select_related(
                "organization",
            ).get(slug=slug, is_active=True)
        except OrganizationInviteLink.DoesNotExist:
            return Response(
                {"detail": "Link no válido."},
                status=status.HTTP_404_NOT_FOUND,
            )

        plans = CoachPricingPlan.objects.filter(
            organization=link.organization, is_active=True,
        ).order_by("price_ars")

        return Response({
            "organization_name": link.organization.name,
            "plans": [
                {"id": p.pk, "name": p.name, "price": str(p.price_ars)}
                for p in plans
            ],
            "currency": "ARS",
        })


class AthleteMySubscriptionView(APIView):
    """
    GET /api/athlete/subscription/
    Returns the authenticated athlete's subscription status.
    Used by AthleteDashboard to show payment status widget.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import AthleteSubscription

        logger.info(
            "athlete.subscription.get",
            extra={
                "event_name": "athlete.subscription.get",
                "user_id": request.user.pk,
                "org_id_param": request.GET.get("org_id"),
                "outcome": "request_received",
            },
        )

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan").first()

        if sub is None:
            return Response({
                "has_subscription": False,
            })

        # PR-152: Calculate trial info
        from django.utils import timezone as tz
        trial_active = False
        trial_days_remaining = 0
        if sub.trial_ends_at:
            remaining = (sub.trial_ends_at - tz.now()).total_seconds()
            if remaining > 0:
                trial_active = True
                trial_days_remaining = max(0, int(remaining / 86400))

        return Response({
            "has_subscription": True,
            "plan_name": sub.coach_plan.name if sub.coach_plan else "",
            "price_ars": str(sub.coach_plan.price_ars) if sub.coach_plan else "0",
            "status": sub.status,
            "next_payment_at": sub.next_payment_at.isoformat() if sub.next_payment_at else None,
            "last_payment_at": sub.last_payment_at.isoformat() if sub.last_payment_at else None,
            "trial_active": trial_active,
            "trial_days_remaining": trial_days_remaining,
            "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
            "paused_at": sub.paused_at.isoformat() if sub.paused_at else None,
            "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
            "pause_reason": sub.pause_reason,
            "cancellation_reason": sub.cancellation_reason,
        })


class AthletePaymentLinkView(APIView):
    """
    GET /api/athlete/payment-link/
    Returns the MercadoPago checkout URL for the athlete's subscription.
    Recovers init_point from existing preapproval, or creates new one.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import AthleteSubscription
        from integrations.mercadopago.subscriptions import get_subscription

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization").first()

        if sub is None:
            return Response(
                {"detail": "No subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Try to recover init_point from existing preapproval
        if sub.mp_preapproval_id:
            try:
                mp_data = get_subscription(sub.mp_preapproval_id)
                init_point = mp_data.get("init_point")
                if init_point:
                    return Response({"init_point": init_point})
            except Exception:
                pass  # Fall through to create new

        # No preapproval or failed to recover — try to create new
        from core.views_onboarding import _create_mp_preapproval
        from core.models import AthleteInvitation

        # Find or create a dummy invitation for the helper
        invitation = AthleteInvitation.objects.filter(
            organization=sub.organization,
            email=request.user.email,
        ).first()

        if invitation:
            mp_data, error = _create_mp_preapproval(
                invitation, request.user.email, coach_plan=sub.coach_plan,
            )
            if mp_data:
                init_point = mp_data.get("init_point")
                preapproval_id = mp_data.get("id")
                sub.mp_preapproval_id = preapproval_id
                sub.save(update_fields=["mp_preapproval_id"])
                return Response({"init_point": init_point})

        return Response(
            {"detail": "No se pudo generar el link de pago. Contactá a tu coach."},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ==============================================================================
# PR-167b: Athlete plan selection — available plans + change plan
# ==============================================================================


class AthleteAvailablePlansView(APIView):
    """
    GET /api/athlete/available-plans/
    Returns the active CoachPricingPlans for the athlete's organization.
    Each plan is annotated with is_current=True if it matches the athlete's current plan.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.models import AthleteSubscription, CoachPricingPlan, Membership

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization").first()

        if sub is None:
            return Response({"detail": "No subscription found."}, status=status.HTTP_404_NOT_FOUND)

        plans = CoachPricingPlan.objects.filter(
            organization=sub.organization, is_active=True,
        ).order_by("price_ars")

        current_plan_id = sub.coach_plan_id

        data = [
            {
                "id": p.pk,
                "name": p.name,
                "description": p.description,
                "price_ars": str(p.price_ars),
                "is_current": p.pk == current_plan_id,
            }
            for p in plans
        ]

        return Response({
            "plans": data,
            "current_plan": {
                "id": sub.coach_plan_id,
                "name": sub.coach_plan.name,
                "price_ars": str(sub.coach_plan.price_ars),
            },
        })


class AthleteChangePlanView(APIView):
    """
    POST /api/athlete/change-plan/
    Body: {"new_plan_id": <pk>}
    Allows an athlete in TRIAL (no MP payment yet) to switch to a different
    active plan within the same organization.
    MP-active subscriptions are out of scope for this PR.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import AthleteSubscription, CoachPricingPlan

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization").first()

        if sub is None:
            return Response({"detail": "No subscription found."}, status=status.HTTP_404_NOT_FOUND)

        new_plan_id = request.data.get("new_plan_id")
        if not new_plan_id:
            return Response({"detail": "new_plan_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate same plan
        try:
            new_plan_id = int(new_plan_id)
        except (TypeError, ValueError):
            return Response({"detail": "new_plan_id inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if new_plan_id == sub.coach_plan_id:
            return Response(
                {"detail": "Ya estás suscripto a ese plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate new plan belongs to same org and is active
        try:
            new_plan = CoachPricingPlan.objects.get(
                pk=new_plan_id, organization=sub.organization, is_active=True,
            )
        except CoachPricingPlan.DoesNotExist:
            return Response(
                {"detail": "Plan no encontrado o inactivo."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only allow plan change during trial (no active MP subscription)
        if sub.mp_preapproval_id:
            return Response(
                {"detail": "El cambio de plan con suscripción activa en MercadoPago no está disponible aún. Contactá a tu coach."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_plan_name = sub.coach_plan.name
        sub.coach_plan = new_plan
        sub.save(update_fields=["coach_plan", "updated_at"])

        logger.info(
            "athlete.change_plan",
            extra={
                "user_id": request.user.pk,
                "organization_id": sub.organization_id,
                "old_plan_id": sub.coach_plan_id,
                "new_plan_id": new_plan.pk,
                "outcome": "changed",
            },
        )

        return Response({
            "status": "changed",
            "new_plan": {
                "id": new_plan.pk,
                "name": new_plan.name,
                "price_ars": str(new_plan.price_ars),
            },
            "message": f"Plan actualizado de {old_plan_name} a {new_plan.name}",
        })


class AthleteSubscriptionSyncView(BillingOrgMixin, APIView):
    """
    POST /api/billing/athlete-subscriptions/sync/

    Safety-net reconciliation with two passes:

    Pass 1 — fast path: subs with mp_preapproval_id → fetch from MP, apply transition.

    Pass 2 — smart path (PR-167f): subs without mp_preapproval_id but whose
    coach_plan has an mp_plan_id → search MP by plan_id for authorized preapprovals,
    match by payer_email, stamp mp_preapproval_id, apply transition.

    Owner / admin only (via BillingOrgMixin.get_org).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import AthleteSubscription, OrgOAuthCredential

        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)

        from core.models import Membership
        membership = Membership.objects.filter(
            user=request.user, organization=org, is_active=True, role__in=["owner", "admin"],
        ).first()
        if not membership:
            return Response({"detail": "Permiso denegado."}, status=status.HTTP_403_FORBIDDEN)

        cred = OrgOAuthCredential.objects.filter(
            organization=org, provider="mercadopago"
        ).first()
        if not cred:
            return Response({"detail": "MercadoPago no conectado para esta organización."}, status=status.HTTP_400_BAD_REQUEST)

        from integrations.mercadopago.athlete_webhook import _apply_status_transition, _notify_owner_payment_received
        from integrations.mercadopago.subscriptions import search_preapprovals

        reconciled = []
        errors = []
        notifications_sent = 0

        # ── Pass 1: subs with mp_preapproval_id ──────────────────────────────
        subs_with_id = list(
            AthleteSubscription.objects.filter(
                organization=org,
                status__in=["pending", "overdue"],
                mp_preapproval_id__isnull=False,
            ).select_related("coach_plan", "athlete__user")
        )

        for sub in subs_with_id:
            try:
                resp = http_requests.get(
                    f"https://api.mercadopago.com/preapproval/{sub.mp_preapproval_id}",
                    headers={"Authorization": f"Bearer {cred.access_token}"},
                    timeout=8,
                )
                if resp.status_code != 200:
                    errors.append({"sub_id": sub.pk, "error": f"MP returned {resp.status_code}"})
                    continue

                mp_data = resp.json()
                mp_status = mp_data.get("status")
                old_status = sub.status
                outcome = _apply_status_transition(sub, mp_status, sub.mp_preapproval_id)
                if outcome == "updated":
                    reconciled.append({
                        "sub_id": sub.pk,
                        "old_status": old_status,
                        "new_status": sub.status,
                    })
                    if sub.status == "active":
                        _notify_owner_payment_received(sub)
                        notifications_sent += 1
            except Exception as exc:
                errors.append({"sub_id": sub.pk, "error": str(exc)})

        # ── Pass 2: subs WITHOUT mp_preapproval_id — 1:1 auto-reconcile ────────
        # MP's GET /users/{id} does not expose email (privacy restriction).
        # Instead: if exactly 1 pending sub and 1 authorized unassigned preapproval
        # exist for a given plan, the match is unambiguous and we auto-link.
        # Multiple subs or multiple preapprovals → log "ambiguous_match" and skip.

        subs_without_id = list(
            AthleteSubscription.objects.filter(
                organization=org,
                status__in=["pending", "overdue"],
                mp_preapproval_id__isnull=True,
                coach_plan__mp_plan_id__isnull=False,
            ).select_related("coach_plan", "athlete__user")
        )

        # Pre-build already-assigned set (includes IDs stamped during Pass 1)
        already_assigned = set(
            AthleteSubscription.objects.filter(
                organization=org,
                mp_preapproval_id__isnull=False,
            ).values_list("mp_preapproval_id", flat=True)
        )

        # Group pending subs by plan_id
        subs_by_plan: dict = {}
        for sub in subs_without_id:
            plan_id = sub.coach_plan.mp_plan_id
            if plan_id:
                subs_by_plan.setdefault(plan_id, []).append(sub)

        for plan_id, plan_subs in subs_by_plan.items():
            try:
                raw_results = search_preapprovals(
                    cred.access_token, plan_id, status="authorized"
                )
            except Exception as exc:
                errors.append({"plan_id": plan_id, "error": str(exc)})
                continue

            # Filter already-assigned; dedup by payer_id keeping newest
            available = [r for r in raw_results if r.get("id") not in already_assigned]
            payer_id_to_preapproval: dict = {}
            for r in available:
                payer_id = str(r.get("payer_id") or "")
                if not payer_id:
                    continue
                existing = payer_id_to_preapproval.get(payer_id)
                if existing is None or (
                    (r.get("date_created") or "") > (existing.get("date_created") or "")
                ):
                    payer_id_to_preapproval[payer_id] = r

            unique_preapprovals = list(payer_id_to_preapproval.values())

            if len(plan_subs) == 1 and len(unique_preapprovals) == 1:
                # 1:1 — unambiguous, safe to auto-reconcile
                sub = plan_subs[0]
                preapproval = unique_preapprovals[0]
                preapproval_id = preapproval.get("id")
                resolved_payer_id = str(preapproval.get("payer_id") or "") or None

                sub.mp_preapproval_id = preapproval_id
                sub.mp_payer_id = resolved_payer_id
                sub.save(update_fields=["mp_preapproval_id", "mp_payer_id", "updated_at"])
                already_assigned.add(preapproval_id)

                old_status = sub.status
                outcome = _apply_status_transition(sub, preapproval.get("status"), preapproval_id)

                logger.info(
                    "mp.sync.reconciled",
                    extra={
                        "event_name": "mp.sync.reconciled",
                        "organization_id": org.pk,
                        "sub_id": sub.pk,
                        "payer_id": resolved_payer_id,
                        "preapproval_id": preapproval_id,
                        "outcome": outcome,
                    },
                )

                if outcome == "updated":
                    reconciled.append({
                        "sub_id": sub.pk,
                        "old_status": old_status,
                        "new_status": sub.status,
                        "reconciled_by": "1_to_1",
                    })
                    if sub.status == "active":
                        notifications_sent += 1
                        # _apply_status_transition already called _notify_owner_payment_received
            else:
                logger.info(
                    "mp.sync.ambiguous_match",
                    extra={
                        "event_name": "mp.sync.ambiguous_match",
                        "organization_id": org.pk,
                        "plan_id": plan_id,
                        "pending_subs": len(plan_subs),
                        "available_preapprovals": len(unique_preapprovals),
                        "outcome": "skipped",
                    },
                )

        logger.info(
            "billing.athlete_sync.completed",
            extra={
                "event_name": "billing.athlete_sync.completed",
                "organization_id": org.pk,
                "reconciled_count": len(reconciled),
                "error_count": len(errors),
                "notifications_sent": notifications_sent,
                "outcome": "ok",
            },
        )

        return Response({"reconciled": reconciled, "errors": errors, "notifications_sent": notifications_sent})


# ==============================================================================
# PR-167c: Athlete subscription lifecycle — Pause / Cancel / Reactivate
# ==============================================================================


def _get_coach_access_token(organization):
    """
    Returns the coach's MP access_token for the given organization, or None.
    Law 6: never log the token.
    """
    from core.models import OrgOAuthCredential
    cred = OrgOAuthCredential.objects.filter(
        organization=organization, provider="mercadopago"
    ).first()
    return cred.access_token if cred else None


def _notify_owner(sub, content, alert_type="subscription_action"):
    """Send InternalMessage to the org owner. Org-scoped. No-op if no owner found."""
    from core.models import InternalMessage, Membership
    owner_membership = (
        Membership.objects.filter(
            organization=sub.organization, role="owner", is_active=True,
        )
        .select_related("user")
        .first()
    )
    if not owner_membership:
        return
    InternalMessage.objects.create(
        organization=sub.organization,
        sender=sub.athlete.user,
        recipient=owner_membership.user,
        content=content,
        alert_type=alert_type,
    )


def _notify_athlete(sub, content, alert_type="subscription_action", sender=None):
    """Send InternalMessage to the athlete. Org-scoped."""
    from core.models import InternalMessage
    InternalMessage.objects.create(
        organization=sub.organization,
        sender=sender or sub.athlete.user,
        recipient=sub.athlete.user,
        content=content,
        alert_type=alert_type,
    )


class AthleteSubscriptionPauseView(APIView):
    """
    POST /api/athlete/subscription/pause/
    Athlete pauses their active subscription.
    Body: {"reason": "injury|vacation|financial|time|other", "comment": "optional"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import AthleteSubscription
        from django.utils import timezone

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization", "athlete__user").first()

        if sub is None:
            return Response({"detail": "No subscription found."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status != AthleteSubscription.Status.ACTIVE:
            return Response(
                {"detail": "Solo se puede pausar una suscripción activa."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")
        comment = request.data.get("comment", "")

        if sub.mp_preapproval_id:
            access_token = _get_coach_access_token(sub.organization)
            if access_token:
                try:
                    from integrations.mercadopago.subscriptions import pause_subscription
                    pause_subscription(access_token, sub.mp_preapproval_id)
                except Exception as exc:
                    logger.error(
                        "athlete_subscription.pause_mp_error",
                        extra={
                            "organization_id": sub.organization_id,
                            "subscription_id": sub.pk,
                            "error": str(exc),
                            "outcome": "error",
                        },
                    )
                    return Response(
                        {"detail": "Error al pausar en MercadoPago."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        now = timezone.now()
        sub.status = AthleteSubscription.Status.PAUSED
        sub.paused_at = now
        sub.pause_reason = reason or None
        sub.pause_comment = comment or None
        sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])

        athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip()
        reason_display = reason or "sin motivo"
        _notify_owner(
            sub,
            f"\u23f8\ufe0f {athlete_name} pausó su suscripción ({reason_display})",
            alert_type="subscription_paused",
        )

        logger.info(
            "athlete_subscription.paused",
            extra={
                "event_name": "athlete_subscription.paused",
                "organization_id": sub.organization_id,
                "subscription_id": sub.pk,
                "user_id": request.user.pk,
                "reason": reason,
                "outcome": "paused",
            },
        )

        return Response({"status": "paused"})


class AthleteSubscriptionCancelView(APIView):
    """
    POST /api/athlete/subscription/cancel/
    Athlete cancels their subscription (active or paused).
    Body: {"reason": "price|injury|time|other_coach|not_using|other", "comment": "optional"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import AthleteSubscription
        from django.utils import timezone

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization", "athlete__user").first()

        if sub is None:
            return Response({"detail": "No subscription found."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status not in (AthleteSubscription.Status.ACTIVE, AthleteSubscription.Status.PAUSED):
            return Response(
                {"detail": "Solo se puede cancelar una suscripción activa o pausada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")
        comment = request.data.get("comment", "")

        if sub.mp_preapproval_id:
            access_token = _get_coach_access_token(sub.organization)
            if access_token:
                try:
                    from integrations.mercadopago.subscriptions import cancel_athlete_subscription
                    cancel_athlete_subscription(access_token, sub.mp_preapproval_id)
                except Exception as exc:
                    logger.error(
                        "athlete_subscription.cancel_mp_error",
                        extra={
                            "organization_id": sub.organization_id,
                            "subscription_id": sub.pk,
                            "error": str(exc),
                            "outcome": "error",
                        },
                    )
                    return Response(
                        {"detail": "Error al cancelar en MercadoPago."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        now = timezone.now()
        sub.status = AthleteSubscription.Status.CANCELLED
        sub.cancelled_at = now
        sub.cancellation_reason = reason or None
        sub.cancellation_comment = comment or None
        sub.paused_at = None
        sub.pause_reason = None
        sub.pause_comment = None
        sub.save(update_fields=[
            "status", "cancelled_at", "cancellation_reason", "cancellation_comment",
            "paused_at", "pause_reason", "pause_comment", "updated_at",
        ])

        athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip()
        reason_display = reason or "sin motivo"
        _notify_owner(
            sub,
            f"\u274c {athlete_name} canceló su suscripción (motivo: {reason_display})",
            alert_type="subscription_cancelled",
        )

        logger.info(
            "athlete_subscription.cancelled",
            extra={
                "event_name": "athlete_subscription.cancelled",
                "organization_id": sub.organization_id,
                "subscription_id": sub.pk,
                "user_id": request.user.pk,
                "reason": reason,
                "outcome": "cancelled",
            },
        )

        return Response({"status": "cancelled"})


class AthleteSubscriptionReactivateView(APIView):
    """
    POST /api/athlete/subscription/reactivate/
    Athlete reactivates a paused or cancelled subscription.
    - paused → authorized in MP → status = active
    - cancelled → new payment link (MP doesn't allow reactivating cancelled)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import AthleteSubscription
        from django.utils import timezone

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan", "organization", "athlete__user").first()

        if sub is None:
            return Response({"detail": "No subscription found."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status not in (AthleteSubscription.Status.PAUSED, AthleteSubscription.Status.CANCELLED):
            return Response(
                {"detail": "Solo se puede reactivar una suscripción pausada o cancelada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip()

        # ── Case 1: paused → reactivate in MP ────────────────────────────────
        if sub.status == AthleteSubscription.Status.PAUSED and sub.mp_preapproval_id:
            access_token = _get_coach_access_token(sub.organization)
            if access_token:
                try:
                    from integrations.mercadopago.subscriptions import reactivate_subscription
                    reactivate_subscription(access_token, sub.mp_preapproval_id)
                except Exception as exc:
                    logger.error(
                        "athlete_subscription.reactivate_mp_error",
                        extra={
                            "organization_id": sub.organization_id,
                            "subscription_id": sub.pk,
                            "error": str(exc),
                            "outcome": "error",
                        },
                    )
                    return Response(
                        {"detail": "Error al reactivar en MercadoPago."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            sub.status = AthleteSubscription.Status.ACTIVE
            sub.paused_at = None
            sub.pause_reason = None
            sub.pause_comment = None
            sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])

            _notify_owner(sub, f"\U0001f504 {athlete_name} reactivó su suscripción", alert_type="subscription_reactivated")

            logger.info(
                "athlete_subscription.reactivated",
                extra={
                    "event_name": "athlete_subscription.reactivated",
                    "organization_id": sub.organization_id,
                    "subscription_id": sub.pk,
                    "user_id": request.user.pk,
                    "outcome": "active",
                },
            )
            return Response({"status": "active"})

        # ── Case 2: paused without MP preapproval (manual activation) ────────
        if sub.status == AthleteSubscription.Status.PAUSED and not sub.mp_preapproval_id:
            sub.status = AthleteSubscription.Status.ACTIVE
            sub.paused_at = None
            sub.pause_reason = None
            sub.pause_comment = None
            sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])
            _notify_owner(sub, f"\U0001f504 {athlete_name} reactivó su suscripción", alert_type="subscription_reactivated")
            return Response({"status": "active"})

        # ── Case 3: cancelled → generate new payment link ─────────────────────
        # MP doesn't allow reactivating cancelled preapprovals.
        # Clear the stale preapproval_id and generate a fresh payment link via
        # the plan's init_point (lazy-creates the preapproval_plan if needed).
        from core.models import OrgOAuthCredential
        from django.conf import settings as django_settings

        cred = OrgOAuthCredential.objects.filter(
            organization=sub.organization, provider="mercadopago"
        ).first()

        if not cred or not sub.coach_plan:
            return Response(
                {"detail": "No se puede generar nuevo link de pago. Contactá a tu coach."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        frontend_url = getattr(django_settings, "FRONTEND_URL", "http://localhost:3000")
        coach_plan = sub.coach_plan

        # Clear the dead preapproval BEFORE calling MP so we never hold a stale ID
        sub.mp_preapproval_id = None
        sub.save(update_fields=["mp_preapproval_id", "updated_at"])

        try:
            if not coach_plan.mp_plan_id:
                # Lazy-create the preapproval_plan in MP (mp_plan_id was nulled or never set)
                from integrations.mercadopago.subscriptions import create_preapproval_plan
                mp_plan = create_preapproval_plan(
                    access_token=cred.access_token,
                    name=f"{sub.organization.name} — {coach_plan.name}",
                    price_ars=coach_plan.price_ars,
                    back_url=f"{frontend_url}/payment/callback",
                )
                coach_plan.mp_plan_id = mp_plan["id"]
                coach_plan.save(update_fields=["mp_plan_id", "updated_at"])
                init_point = mp_plan.get("init_point")
            else:
                # Plan already registered in MP — fetch it to get its checkout URL
                from integrations.mercadopago.subscriptions import get_preapproval_plan
                mp_plan = get_preapproval_plan(
                    access_token=cred.access_token,
                    plan_id=coach_plan.mp_plan_id,
                )
                init_point = mp_plan.get("init_point")
        except Exception as exc:
            logger.error(
                "athlete_subscription.reactivate_new_preapproval_error",
                extra={
                    "organization_id": sub.organization_id,
                    "subscription_id": sub.pk,
                    "error": str(exc),
                    "outcome": "error",
                },
            )
            return Response(
                {"detail": "Error al generar link de pago en MercadoPago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not init_point:
            return Response(
                {"detail": "MercadoPago no retornó un link de pago."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub.status = AthleteSubscription.Status.PENDING
        sub.cancelled_at = None
        sub.cancellation_reason = None
        sub.cancellation_comment = None
        sub.save(update_fields=[
            "status", "cancelled_at",
            "cancellation_reason", "cancellation_comment", "updated_at",
        ])

        _notify_owner(sub, f"\U0001f504 {athlete_name} reactivó su suscripción", alert_type="subscription_reactivated")

        logger.info(
            "athlete_subscription.reactivate_new_preapproval",
            extra={
                "event_name": "athlete_subscription.reactivate_new_preapproval",
                "organization_id": sub.organization_id,
                "subscription_id": sub.pk,
                "user_id": request.user.pk,
                "outcome": "pending",
            },
        )

        return Response({"status": "pending", "redirect_url": init_point})


class OwnerSubscriptionActionView(BillingOrgMixin, APIView):
    """
    POST /api/billing/athlete-subscriptions/<pk>/owner-action/
    Owner/admin pauses, cancels, or reactivates an athlete's subscription.
    Body: {"action": "pause|cancel|reactivate", "reason": "owner_decision", "comment": "optional"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from core.models import AthleteSubscription, Membership
        from django.utils import timezone

        org = self.get_org(request)
        if org is None:
            return Response({"detail": "No organization context."}, status=status.HTTP_403_FORBIDDEN)

        try:
            membership = Membership.objects.get(user=request.user, organization=org, is_active=True)
        except Membership.DoesNotExist:
            return Response({"detail": "Sin acceso."}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in ("owner", "admin"):
            return Response({"detail": "Solo owner o admin."}, status=status.HTTP_403_FORBIDDEN)

        try:
            sub = AthleteSubscription.objects.select_related(
                "athlete__user", "coach_plan", "organization"
            ).get(pk=pk, organization=org)
        except AthleteSubscription.DoesNotExist:
            return Response({"detail": "Suscripción no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action", "")
        reason = request.data.get("reason", "owner_decision")
        comment = request.data.get("comment", "")
        now = timezone.now()
        athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip()

        # ── PAUSE ─────────────────────────────────────────────────────────────
        if action == "pause":
            if sub.status != AthleteSubscription.Status.ACTIVE:
                return Response(
                    {"detail": "Solo se puede pausar una suscripción activa."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if sub.mp_preapproval_id:
                access_token = _get_coach_access_token(sub.organization)
                if access_token:
                    try:
                        from integrations.mercadopago.subscriptions import pause_subscription
                        pause_subscription(access_token, sub.mp_preapproval_id)
                    except Exception as exc:
                        logger.error(
                            "owner.subscription.pause_mp_error",
                            extra={
                                "organization_id": org.pk,
                                "subscription_id": sub.pk,
                                "error": str(exc),
                            },
                        )
                        return Response({"detail": "Error al pausar en MercadoPago."}, status=status.HTTP_502_BAD_GATEWAY)

            sub.status = AthleteSubscription.Status.PAUSED
            sub.paused_at = now
            sub.pause_reason = reason or None
            sub.pause_comment = comment or None
            sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])
            _notify_athlete(sub, "Tu coach pausó tu suscripción", alert_type="subscription_paused", sender=request.user)

            logger.info(
                "owner.subscription.paused",
                extra={
                    "event_name": "owner.subscription.paused",
                    "organization_id": org.pk,
                    "subscription_id": sub.pk,
                    "owner_id": request.user.pk,
                    "outcome": "paused",
                },
            )
            return Response({"status": "paused"})

        # ── CANCEL ────────────────────────────────────────────────────────────
        if action == "cancel":
            if sub.status not in (AthleteSubscription.Status.ACTIVE, AthleteSubscription.Status.PAUSED):
                return Response(
                    {"detail": "Solo se puede cancelar una suscripción activa o pausada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if sub.mp_preapproval_id:
                access_token = _get_coach_access_token(sub.organization)
                if access_token:
                    try:
                        from integrations.mercadopago.subscriptions import cancel_athlete_subscription
                        cancel_athlete_subscription(access_token, sub.mp_preapproval_id)
                    except Exception as exc:
                        logger.error(
                            "owner.subscription.cancel_mp_error",
                            extra={
                                "organization_id": org.pk,
                                "subscription_id": sub.pk,
                                "error": str(exc),
                            },
                        )
                        return Response({"detail": "Error al cancelar en MercadoPago."}, status=status.HTTP_502_BAD_GATEWAY)

            sub.status = AthleteSubscription.Status.CANCELLED
            sub.cancelled_at = now
            sub.cancellation_reason = reason or None
            sub.cancellation_comment = comment or None
            sub.paused_at = None
            sub.pause_reason = None
            sub.pause_comment = None
            sub.save(update_fields=[
                "status", "cancelled_at", "cancellation_reason", "cancellation_comment",
                "paused_at", "pause_reason", "pause_comment", "updated_at",
            ])
            _notify_athlete(sub, "Tu coach canceló tu suscripción", alert_type="subscription_cancelled", sender=request.user)

            logger.info(
                "owner.subscription.cancelled",
                extra={
                    "event_name": "owner.subscription.cancelled",
                    "organization_id": org.pk,
                    "subscription_id": sub.pk,
                    "owner_id": request.user.pk,
                    "outcome": "cancelled",
                },
            )
            return Response({"status": "cancelled"})

        # ── REACTIVATE ────────────────────────────────────────────────────────
        if action == "reactivate":
            if sub.status not in (AthleteSubscription.Status.PAUSED, AthleteSubscription.Status.CANCELLED):
                return Response(
                    {"detail": "Solo se puede reactivar una suscripción pausada o cancelada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if sub.status == AthleteSubscription.Status.PAUSED and sub.mp_preapproval_id:
                access_token = _get_coach_access_token(sub.organization)
                if access_token:
                    try:
                        from integrations.mercadopago.subscriptions import reactivate_subscription
                        reactivate_subscription(access_token, sub.mp_preapproval_id)
                    except Exception as exc:
                        logger.error(
                            "owner.subscription.reactivate_mp_error",
                            extra={
                                "organization_id": org.pk,
                                "subscription_id": sub.pk,
                                "error": str(exc),
                            },
                        )
                        return Response({"detail": "Error al reactivar en MercadoPago."}, status=status.HTTP_502_BAD_GATEWAY)

                sub.status = AthleteSubscription.Status.ACTIVE
                sub.paused_at = None
                sub.pause_reason = None
                sub.pause_comment = None
                sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])
                _notify_athlete(sub, "Tu coach reactivó tu suscripción", alert_type="subscription_reactivated", sender=request.user)

            elif sub.status == AthleteSubscription.Status.PAUSED and not sub.mp_preapproval_id:
                sub.status = AthleteSubscription.Status.ACTIVE
                sub.paused_at = None
                sub.pause_reason = None
                sub.pause_comment = None
                sub.save(update_fields=["status", "paused_at", "pause_reason", "pause_comment", "updated_at"])
                _notify_athlete(sub, "Tu coach reactivó tu suscripción", alert_type="subscription_reactivated", sender=request.user)

            else:
                # cancelled → mark pending; athlete must pay again
                sub.status = AthleteSubscription.Status.PENDING
                sub.cancelled_at = None
                sub.cancellation_reason = None
                sub.cancellation_comment = None
                sub.mp_preapproval_id = None
                sub.save(update_fields=[
                    "status", "cancelled_at", "cancellation_reason", "cancellation_comment",
                    "mp_preapproval_id", "updated_at",
                ])
                _notify_athlete(
                    sub,
                    "Tu coach reactivó tu suscripción. Completá el pago para acceder.",
                    alert_type="subscription_reactivated",
                    sender=request.user,
                )

            logger.info(
                "owner.subscription.reactivated",
                extra={
                    "event_name": "owner.subscription.reactivated",
                    "organization_id": org.pk,
                    "subscription_id": sub.pk,
                    "owner_id": request.user.pk,
                    "outcome": sub.status,
                },
            )
            return Response({"status": sub.status})

        return Response(
            {"detail": "Acción inválida. Debe ser pause, cancel o reactivate."},
            status=status.HTTP_400_BAD_REQUEST,
        )
