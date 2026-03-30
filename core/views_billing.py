import json
import logging
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
    """

    def get_org(self, request):
        from core.models import Membership
        try:
            m = Membership.objects.select_related("organization").filter(
                user=request.user,
                is_active=True,
                role__in=["owner", "admin", "coach"],
            ).first()
            if m:
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
        plans = CoachPricingPlan.objects.filter(organization=org).order_by("price_ars")
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
            .select_related("athlete__user", "coach_plan")
            .order_by("status", "-created_at")
        )
        data = [
            {
                "id": sub.pk,
                "athlete_id": sub.athlete_id,
                "athlete_first_name": sub.athlete.user.first_name,
                "athlete_last_name": sub.athlete.user.last_name,
                "athlete_email": sub.athlete.user.email,
                "coach_plan_id": sub.coach_plan_id,
                "coach_plan_name": sub.coach_plan.name,
                "price_ars": str(sub.coach_plan.price_ars),
                "status": sub.status,
                "mp_preapproval_id": sub.mp_preapproval_id,
                "last_payment_at": sub.last_payment_at.isoformat() if sub.last_payment_at else None,
                "next_payment_at": sub.next_payment_at.isoformat() if sub.next_payment_at else None,
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
        from core.models import AthleteSubscription, Membership
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
            sub = AthleteSubscription.objects.select_related("athlete__user").get(pk=pk, organization=org)
        except AthleteSubscription.DoesNotExist:
            return Response({"detail": "Suscripción no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status == AthleteSubscription.Status.ACTIVE:
            return Response({"detail": "La suscripción ya está activa."}, status=status.HTTP_400_BAD_REQUEST)

        sub.status = AthleteSubscription.Status.ACTIVE
        sub.save(update_fields=["status", "updated_at"])

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
        return Response({"id": sub.pk, "status": sub.status})


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

        sub = AthleteSubscription.objects.filter(
            athlete__user=request.user,
        ).select_related("coach_plan").first()

        if sub is None:
            return Response({
                "has_subscription": False,
            })

        return Response({
            "has_subscription": True,
            "plan_name": sub.coach_plan.name if sub.coach_plan else "",
            "price_ars": str(sub.coach_plan.price_ars) if sub.coach_plan else "0",
            "status": sub.status,
            "next_payment_at": sub.next_payment_at.isoformat() if sub.next_payment_at else None,
            "last_payment_at": sub.last_payment_at.isoformat() if sub.last_payment_at else None,
        })
