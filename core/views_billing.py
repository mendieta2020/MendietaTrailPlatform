import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

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
