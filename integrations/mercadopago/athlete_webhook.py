import logging
import requests

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "authorized": "active",
    "paused": "overdue",
    "cancelled": "cancelled",
    "pending": None,  # no-op
}


def _apply_status_transition(sub, mp_status, preapproval_id):
    """
    Apply STATUS_MAP transition to sub and save.
    Returns "updated", "noop", or raises.
    Idempotent — safe to rerun.
    """
    from django.utils import timezone
    from datetime import timedelta

    new_status = STATUS_MAP.get(mp_status)
    if new_status is None:
        return "noop"
    if sub.status == new_status:
        return "noop"

    sub.status = new_status
    if new_status == "active":
        now = timezone.now()
        sub.last_payment_at = now
        sub.next_payment_at = now + timedelta(days=30)
    sub.save(update_fields=["status", "last_payment_at", "next_payment_at", "updated_at"])

    logger.info(
        "athlete_subscription_updated",
        extra={
            "event": "athlete_subscription_updated",
            "preapproval_id": preapproval_id,
            "new_status": new_status,
            "subscription_id": sub.id,
        },
    )
    return "updated"


def _fetch_preapproval_with_any_coach_token(preapproval_id):
    """
    Try each OrgOAuthCredential(provider="mercadopago") until one returns a 200 for
    GET /preapproval/{preapproval_id}.

    Returns (mp_data dict, OrgOAuthCredential) on first success, or (None, None).
    Never logs access_token (Law 6).
    """
    from core.models import OrgOAuthCredential

    credentials = OrgOAuthCredential.objects.filter(provider="mercadopago").select_related("organization")
    for cred in credentials:
        try:
            resp = requests.get(  # noqa: requests imported at module level
                f"https://api.mercadopago.com/preapproval/{preapproval_id}",
                headers={"Authorization": f"Bearer {cred.access_token}"},
                timeout=8,
            )
            if resp.status_code == 200:
                return resp.json(), cred
        except Exception:
            continue
    return None, None


def _reconcile_by_payer(mp_data, cred):
    """
    Fallback match: find AthleteSubscription by payer_email + preapproval_plan_id
    within organizations owned by this credential.

    Returns AthleteSubscription or None.
    """
    from core.models import AthleteSubscription

    payer_email = (mp_data.get("payer_email") or "").lower().strip()
    preapproval_plan_id = mp_data.get("preapproval_plan_id") or mp_data.get("plan_id") or ""

    if not payer_email or not preapproval_plan_id:
        return None

    return (
        AthleteSubscription.objects.filter(
            organization=cred.organization,
            coach_plan__mp_plan_id=preapproval_plan_id,
            athlete__user__email__iexact=payer_email,
        )
        .select_related("coach_plan", "athlete__user")
        .order_by("-created_at")
        .first()
    )


def process_athlete_subscription_webhook(payload: dict) -> dict:
    """
    Procesa eventos de MP para AthleteSubscription.
    Idempotente — safe to rerun multiple times.

    Fast path: lookup by mp_preapproval_id.
    Fallback path: fetch preapproval from MP, match by payer_email + plan_id.

    Eventos que maneja:
    - authorized  → status = "active", last_payment_at = now()
    - paused      → status = "overdue"
    - cancelled   → status = "cancelled"
    - pending     → no-op (ya está en pending)

    Returns: {"outcome": "updated"|"noop"|"not_found"|"reconciled",
              "preapproval_id": str}
    """
    preapproval_id = payload.get("id") or payload.get("data", {}).get("id")
    if not preapproval_id:
        return {"outcome": "noop", "preapproval_id": None}

    # Lazy import (Law 4)
    from core.models import AthleteSubscription

    # ── Fast path ────────────────────────────────────────────────────────────
    try:
        sub = AthleteSubscription.objects.get(mp_preapproval_id=preapproval_id)
        mp_status = payload.get("status")
        outcome = _apply_status_transition(sub, mp_status, preapproval_id)
        return {"outcome": outcome, "preapproval_id": preapproval_id}
    except AthleteSubscription.DoesNotExist:
        pass

    # ── Fallback: fetch from MP and reconcile by payer ────────────────────────
    mp_data, cred = _fetch_preapproval_with_any_coach_token(preapproval_id)
    if mp_data is not None and cred is not None:
        sub = _reconcile_by_payer(mp_data, cred)
        if sub is not None:
            # Stamp the real preapproval_id so future webhooks hit the fast path
            sub.mp_preapproval_id = preapproval_id
            sub.save(update_fields=["mp_preapproval_id", "updated_at"])

            mp_status = mp_data.get("status") or payload.get("status")
            outcome = _apply_status_transition(sub, mp_status, preapproval_id)

            logger.info(
                "mp.athlete_webhook.reconciled",
                extra={
                    "event_name": "mp.athlete_webhook.reconciled",
                    "preapproval_id": preapproval_id,
                    "subscription_id": sub.id,
                    "organization_id": cred.organization_id,
                    "outcome": outcome,
                },
            )
            return {"outcome": "reconciled", "preapproval_id": preapproval_id}

    logger.warning(
        "mp.athlete_webhook.not_found",
        extra={"preapproval_id": preapproval_id, "outcome": "not_found"},
    )
    return {"outcome": "not_found", "preapproval_id": preapproval_id}
