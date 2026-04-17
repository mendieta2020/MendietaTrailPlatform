"""
Management command: daily_mp_reconciliation

For each active MercadoPago credential, checks AthleteSubscription records
in pending/overdue status and tries to reconcile them against MP's real state.

Idempotent — safe to rerun multiple times.

Deploy: run daily at 3am ART (= 6am UTC)
    cron: "0 6 * * *"
    command: python manage.py daily_mp_reconciliation

Usage:
    python manage.py daily_mp_reconciliation
"""

import logging

import requests
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile pending/overdue AthleteSubscriptions against MercadoPago."

    def handle(self, *args, **options):
        from core.models import AthleteSubscription, OrgOAuthCredential, InternalMessage, Membership

        credentials = OrgOAuthCredential.objects.filter(
            provider="mercadopago"
        ).select_related("organization")

        if not credentials.exists():
            self.stdout.write("No MercadoPago credentials found. Exiting.")
            return

        total_reconciled = 0
        total_orphans = 0
        total_errors = 0

        for cred in credentials:
            org = cred.organization
            subs = AthleteSubscription.objects.filter(
                organization=org,
                status__in=["pending", "overdue"],
                mp_preapproval_id__isnull=False,
            ).select_related("coach_plan", "athlete__user")

            if not subs.exists():
                continue

            self.stdout.write(f"\nOrg: {org.name} ({org.id}) — {subs.count()} subs to check")

            for sub in subs:
                try:
                    resp = requests.get(
                        f"https://api.mercadopago.com/preapproval/{sub.mp_preapproval_id}",
                        headers={"Authorization": f"Bearer {cred.access_token}"},
                        timeout=8,
                    )
                    if resp.status_code != 200:
                        self.stdout.write(
                            f"  sub {sub.id}: MP returned {resp.status_code} — skip"
                        )
                        total_errors += 1
                        continue

                    mp_data = resp.json()
                    mp_status = mp_data.get("status", "")

                    if mp_status == "authorized" and sub.status in ("pending", "overdue"):
                        from integrations.mercadopago.athlete_webhook import _apply_status_transition
                        outcome = _apply_status_transition(sub, mp_status, sub.mp_preapproval_id)
                        if outcome == "updated":
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  sub {sub.id}: reconciled pending→active"
                                )
                            )
                            logger.info(
                                "mp.daily_reconciliation.fixed",
                                extra={
                                    "event_name": "mp.daily_reconciliation.fixed",
                                    "organization_id": org.id,
                                    "subscription_id": sub.id,
                                    "preapproval_id": sub.mp_preapproval_id,
                                    "outcome": "fixed",
                                },
                            )
                            total_reconciled += 1
                        else:
                            self.stdout.write(f"  sub {sub.id}: noop (already updated)")

                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(f"  sub {sub.id}: error — {exc}")
                    )
                    logger.error(
                        "mp.daily_reconciliation.error",
                        extra={
                            "event_name": "mp.daily_reconciliation.error",
                            "subscription_id": sub.id,
                            "error": str(exc),
                            "outcome": "error",
                        },
                    )
                    total_errors += 1

            # Orphan check: search MP for authorized preapprovals with no matching sub
            try:
                from integrations.mercadopago.subscriptions import search_preapprovals
                coach_plans = org.coach_pricing_plans.filter(mp_plan_id__isnull=False)
                for plan in coach_plans:
                    mp_results = search_preapprovals(cred.access_token, plan.mp_plan_id, status="authorized")
                    for mp_preapproval in mp_results:
                        pid = mp_preapproval.get("id")
                        if not pid:
                            continue
                        exists = AthleteSubscription.objects.filter(
                            organization=org,
                            mp_preapproval_id=pid,
                        ).exists()
                        if not exists:
                            logger.warning(
                                "mp.daily_reconciliation.orphan",
                                extra={
                                    "event_name": "mp.daily_reconciliation.orphan",
                                    "organization_id": org.id,
                                    "mp_plan_id": plan.mp_plan_id,
                                    "preapproval_id": pid,
                                    "outcome": "orphan",
                                },
                            )
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  ORPHAN: authorized preapproval {pid} has no AthleteSubscription"
                                )
                            )
                            total_orphans += 1
                            # Notify org owner
                            _notify_orphan(org, plan, pid)
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  Orphan check error for {org.name}: {exc}")
                )

        self.stdout.write("\n=== Summary ===")
        self.stdout.write(f"  reconciled: {total_reconciled}")
        self.stdout.write(f"  orphans:    {total_orphans}")
        self.stdout.write(f"  errors:     {total_errors}")


def _notify_orphan(org, plan, preapproval_id):
    """Notify org owner about an orphaned authorized preapproval."""
    from core.models import InternalMessage, Membership
    from django.contrib.auth import get_user_model

    User = get_user_model()

    owner_membership = (
        Membership.objects.filter(
            organization=org, role="owner", is_active=True
        )
        .select_related("user")
        .first()
    )
    if not owner_membership:
        return

    InternalMessage.objects.create(
        organization=org,
        sender=owner_membership.user,
        recipient=owner_membership.user,
        content=(
            f"\u26a0\ufe0f Pago huérfano detectado: preapproval {preapproval_id} "
            f"(plan {plan.name}) está autorizado en MercadoPago pero no tiene "
            f"suscripción en Quantoryn. Verificar manualmente."
        ),
        alert_type="orphan_payment",
    )
