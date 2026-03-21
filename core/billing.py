import logging
from functools import wraps
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def require_plan(min_plan: str):
    """DRF decorator: blocks with HTTP 402 if the org's plan is insufficient."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(view_instance, request, *args, **kwargs):
            org = getattr(request, "auth_organization", None)
            if org is None:
                return view_func(view_instance, request, *args, **kwargs)
            try:
                subscription = org.subscription
            except Exception:
                subscription = None

            has_access = subscription is not None and subscription.has_plan(min_plan)

            if not has_access:
                logger.info("billing.gate.denied", extra={
                    "organization_id": getattr(org, "pk", None),
                    "required_plan": min_plan,
                    "current_plan": getattr(subscription, "plan", "none"),
                    "outcome": "denied",
                })
                return Response(
                    {
                        "detail": f"This feature requires the '{min_plan}' plan or higher.",
                        "required_plan": min_plan,
                        "current_plan": getattr(subscription, "plan", "free"),
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
            return view_func(view_instance, request, *args, **kwargs)
        return wrapper
    return decorator
