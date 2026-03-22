import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

from core.billing import require_plan  # plan gate decorator

logger = logging.getLogger(__name__)


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


class BillingStatusView(APIView):
    """
    GET /api/billing/status/
    Returns the subscription state for the request's organization.
    Accessible by coach and owner.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.serializers_billing import BillingStatusSerializer
        from core.models import OrganizationSubscription
        org = getattr(request, "auth_organization", None)
        if org is None:
            return Response(
                {"detail": "No organization context."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            subscription = OrganizationSubscription.objects.get(organization=org)
        except OrganizationSubscription.DoesNotExist:
            return Response(
                {"detail": "No subscription found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = BillingStatusSerializer(subscription)
        return Response(serializer.data)


class BillingSubscribeView(APIView):
    """
    POST /api/billing/subscribe/
    Body: {"plan_id": <SubscriptionPlan pk>}
    Creates a MercadoPago subscription and returns init_point (checkout URL).
    Only coaches/owners. Plan must have mp_plan_id configured.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import SubscriptionPlan, OrganizationSubscription
        org = getattr(request, "auth_organization", None)
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


class BillingCancelView(APIView):
    """
    POST /api/billing/cancel/
    Cancels the organization's active MP subscription and marks it as inactive locally.
    Only coaches/owners.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import OrganizationSubscription
        org = getattr(request, "auth_organization", None)
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


class MPConnectView(APIView):
    """
    GET /api/billing/mp/connect/
    Returns the MercadoPago authorization URL. The frontend redirects the coach
    there to grant Quantoryn access to their MP account.
    Requires: authenticated user, pro plan.
    """

    permission_classes = [IsAuthenticated]

    @require_plan("pro")
    def get(self, request):
        from integrations.mercadopago.oauth import mp_get_authorization_url  # lazy — Law 4

        org = getattr(request, "auth_organization", None)
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
        return django_redirect(f"{frontend_url}/settings/billing?mp_connected=true")


class MPDisconnectView(APIView):
    """
    DELETE /api/billing/mp/disconnect/
    Removes the coach's MP OAuth credential for this organization.
    Requires: authenticated user, pro plan.
    """

    permission_classes = [IsAuthenticated]

    @require_plan("pro")
    def delete(self, request):
        from core.models import OrgOAuthCredential

        org = getattr(request, "auth_organization", None)
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
