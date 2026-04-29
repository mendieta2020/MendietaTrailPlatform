import logging
import requests

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "authorized": "active",
    "paused": "paused",
    "cancelled": "cancelled",
    "overdue": "overdue",   # PR-169: MP could not charge — failed payment
    "pending": None,        # no-op
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

    if new_status == "active":
        _notify_owner_payment_received(sub)
    elif new_status == "overdue":
        _notify_failed_payment(sub)

    return "updated"


def _notify_owner_payment_received(sub):
    """
    Creates an InternalMessage to the org owner when an athlete's subscription
    transitions to active. Org-scoped (Law 1). No-op if no active owner found.
    """
    from core.models import InternalMessage, Membership

    owner_membership = (
        Membership.objects.filter(
            organization=sub.organization, role="owner", is_active=True
        )
        .select_related("user")
        .first()
    )
    if not owner_membership:
        return

    athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip()
    plan_name = sub.coach_plan.name if sub.coach_plan else "Sin plan"
    InternalMessage.objects.create(
        organization=sub.organization,
        sender=sub.athlete.user,
        recipient=owner_membership.user,
        content=f"\U0001f4b0 {athlete_name} activó su suscripción al plan {plan_name}",
        alert_type="payment_received",
    )
    logger.info(
        "mp.payment_received.owner_notified",
        extra={
            "event_name": "mp.payment_received.owner_notified",
            "organization_id": sub.organization_id,
            "subscription_id": sub.id,
            "outcome": "notified",
        },
    )


def _notify_failed_payment(sub):
    """
    PR-169: When a subscription transitions to overdue (MP could not charge),
    notify both the org owner and the athlete.
    - Owner: urgent alert to follow up.
    - Athlete: informational — asks them to update their payment method.
    - Does NOT cancel the subscription (gives athlete a chance to fix card).
    Org-scoped (Law 1). No-op if no owner found.
    """
    from core.models import InternalMessage, Membership

    owner_membership = (
        Membership.objects.filter(
            organization=sub.organization, role="owner", is_active=True
        )
        .select_related("user")
        .first()
    )

    athlete_name = f"{sub.athlete.user.first_name} {sub.athlete.user.last_name}".strip() or sub.athlete.user.username
    plan_name = sub.coach_plan.name if sub.coach_plan else "Sin plan"

    if owner_membership:
        InternalMessage.objects.create(
            organization=sub.organization,
            sender=sub.athlete.user,
            recipient=owner_membership.user,
            content=(
                f"\u26a0\ufe0f Pago fallido: {athlete_name} — "
                f"no se pudo cobrar el plan {plan_name}. "
                f"Solicitarle que actualice su método de pago urgente."
            ),
            alert_type="payment_failed",
        )
        # Notify athlete (sender = owner, recipient = athlete)
        InternalMessage.objects.create(
            organization=sub.organization,
            sender=owner_membership.user,
            recipient=sub.athlete.user,
            content=(
                f"\U0001f4b3 No pudimos procesar tu pago para el plan {plan_name}. "
                f"Actualizá tu tarjeta en MercadoPago para no perder acceso. "
                f"Si ya lo hiciste, el estado se actualizará en las próximas horas."
            ),
            alert_type="payment_failed",
        )

    logger.info(
        "mp.payment_failed.notified",
        extra={
            "event_name": "mp.payment_failed.notified",
            "organization_id": sub.organization_id,
            "subscription_id": sub.id,
            "outcome": "notified",
        },
    )


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
    Fallback match: find AthleteSubscription for a preapproval whose id is unknown.

    Strategy (in order):
    1. Match by mp_payer_id field (fastest — no extra API call).
    2. Match by payer_email from mp_data (populated for some MP flows).
    3. Resolve email via GET /users/{payer_id} and match by email (PR-167f-fix).

    Returns AthleteSubscription or None. Stores mp_payer_id when resolved via
    email lookup so future calls skip the API round-trip.
    Law 6: access_token never logged.
    """
    from core.models import AthleteSubscription

    payer_id = str(mp_data.get("payer_id") or "")
    payer_email = (mp_data.get("payer_email") or "").lower().strip()
    preapproval_plan_id = mp_data.get("preapproval_plan_id") or mp_data.get("plan_id") or ""

    # 1. Fast lookup by mp_payer_id (set during sync or a prior webhook reconcile)
    if payer_id:
        sub = (
            AthleteSubscription.objects.filter(
                organization=cred.organization,
                mp_payer_id=payer_id,
            )
            .select_related("coach_plan", "athlete__user")
            .order_by("-created_at")
            .first()
        )
        if sub is not None:
            return sub

    # 2. Match by payer_email directly from mp_data (may be populated)
    if payer_email and preapproval_plan_id:
        sub = (
            AthleteSubscription.objects.filter(
                organization=cred.organization,
                coach_plan__mp_plan_id=preapproval_plan_id,
                athlete__user__email__iexact=payer_email,
            )
            .select_related("coach_plan", "athlete__user")
            .order_by("-created_at")
            .first()
        )
        if sub is not None:
            return sub

    # 3. Resolve email via MP API (payer_email empty — production case)
    if payer_id and preapproval_plan_id:
        try:
            from integrations.mercadopago.subscriptions import get_mp_user
            mp_user = get_mp_user(cred.access_token, payer_id)
            resolved_email = (mp_user.get("email") or "").lower().strip()
            if resolved_email:
                sub = (
                    AthleteSubscription.objects.filter(
                        organization=cred.organization,
                        coach_plan__mp_plan_id=preapproval_plan_id,
                        athlete__user__email__iexact=resolved_email,
                    )
                    .select_related("coach_plan", "athlete__user")
                    .order_by("-created_at")
                    .first()
                )
                if sub is not None:
                    # Store payer_id so future calls skip this API round-trip
                    sub.mp_payer_id = payer_id
                    sub.save(update_fields=["mp_payer_id", "updated_at"])
                    return sub
        except Exception as exc:
            logger.warning(
                "mp.reconcile.user_lookup_failed",
                extra={
                    "event_name": "mp.reconcile.user_lookup_failed",
                    "payer_id": payer_id,
                    "error": str(exc),
                },
            )

    # 4. Match by preapproval_plan_id only — no email required (handles email mismatch case)
    if preapproval_plan_id:
        candidate_qs = AthleteSubscription.objects.filter(
            organization=cred.organization,
            coach_plan__mp_plan_id=preapproval_plan_id,
            mp_preapproval_id__isnull=True,
            status__in=["pending", "active", "overdue"],
        )
        count = candidate_qs.count()
        if count == 1:
            sub = candidate_qs.select_related("coach_plan", "athlete__user").first()
            stamped_preapproval_id = str(mp_data.get("id") or "")
            sub.mp_preapproval_id = stamped_preapproval_id
            update_fields = ["mp_preapproval_id", "updated_at"]
            if payer_id:
                sub.mp_payer_id = payer_id
                update_fields.append("mp_payer_id")
            sub.save(update_fields=update_fields)
            logger.info(
                "mp.webhook.reconciled_by_plan_id",
                extra={
                    "event_name": "mp.webhook.reconciled_by_plan_id",
                    "preapproval_id": stamped_preapproval_id,
                    "subscription_id": sub.id,
                    "organization_id": cred.organization_id,
                    "outcome": "stamped",
                },
            )
            return sub
        elif count > 1:
            logger.warning(
                "mp.webhook.reconcile_ambiguous",
                extra={
                    "event_name": "mp.webhook.reconcile_ambiguous",
                    "count": count,
                    "plan_id": preapproval_plan_id,
                },
            )
            return None

    return None


def _resolve_preapproval_from_payment(payment_id: str) -> str | None:
    """
    Resolve preapproval_id from a payment_id via the MP payments API.
    Checks metadata.preapproval_id first, then
    point_of_interaction.transaction_data.subscription_id.
    Tries each OrgOAuthCredential token. Law 6: access_token never logged.
    """
    from core.models import OrgOAuthCredential
    from integrations.mercadopago.subscriptions import get_mp_payment

    credentials = OrgOAuthCredential.objects.filter(provider="mercadopago")
    for cred in credentials:
        try:
            payment = get_mp_payment(cred.access_token, str(payment_id))
            meta_preapproval = (payment.get("metadata") or {}).get("preapproval_id")
            if meta_preapproval:
                return str(meta_preapproval)
            poi = ((payment.get("point_of_interaction") or {}).get("transaction_data") or {})
            if poi.get("subscription_id"):
                return str(poi["subscription_id"])
        except Exception:
            continue
    return None


def process_athlete_subscription_webhook(payload: dict, webhook_type: str | None = None) -> dict:
    """
    Procesa eventos de MP para AthleteSubscription.
    Idempotente — safe to rerun multiple times.

    webhook_type: query-string ``type`` from the MP webhook URL.
      - "subscription_preapproval": payload.data.id IS the preapproval_id  (fast path)
      - "payment" or "subscription_authorized_payment": payload.data.id is a
        payment_id; we resolve the linked preapproval_id via the MP payments API.
      - None: backward-compat fallback — treated as subscription_preapproval.

    Fast path: lookup by mp_preapproval_id.
    Fallback path: fetch preapproval from MP, match by payer_email + plan_id.

    Returns: {"outcome": "updated"|"noop"|"not_found"|"reconciled",
              "preapproval_id": str}
    """
    payload_id = payload.get("id") or payload.get("data", {}).get("id")
    if not payload_id:
        return {"outcome": "noop", "preapproval_id": None}

    if webhook_type in ("payment", "subscription_authorized_payment"):
        preapproval_id = _resolve_preapproval_from_payment(payload_id)
        if preapproval_id is None:
            logger.info(
                "mp.athlete_webhook.payment_no_preapproval",
                extra={
                    "event_name": "mp.athlete_webhook.payment_no_preapproval",
                    "payment_id": payload_id,
                    "webhook_type": webhook_type,
                    "outcome": "skipped",
                    "reason_code": "NO_PREAPPROVAL_LINKED",
                },
            )
            return {"outcome": "noop", "preapproval_id": None}
    else:
        preapproval_id = str(payload_id)

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
