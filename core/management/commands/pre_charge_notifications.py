"""
Management command: pre_charge_notifications

Sends a reminder InternalMessage to athletes whose active subscription renews
in 3–4 days. Idempotent — uses last_pre_charge_notification_sent_at to avoid
duplicate messages for the same renewal date.

Deploy: run daily at 3am ART (= 6am UTC), same cron as daily_mp_reconciliation.
    cron: "0 6 * * *"
    command: python manage.py pre_charge_notifications

Usage:
    python manage.py pre_charge_notifications
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send pre-charge reminders to athletes 3 days before subscription renewal."

    def handle(self, *args, **options):
        from core.models import AthleteSubscription, InternalMessage, Membership

        now = timezone.now()
        window_start = now + timedelta(days=3)
        window_end = now + timedelta(days=4)

        subs = AthleteSubscription.objects.filter(
            status="active",
            next_payment_at__gte=window_start,
            next_payment_at__lt=window_end,
        ).select_related("coach_plan", "athlete__user", "organization")

        if not subs.exists():
            self.stdout.write("No subscriptions renewing in 3 days.")
            return

        self.stdout.write(f"Found {subs.count()} subscription(s) renewing in 3 days.")

        sent = 0
        skipped = 0

        for sub in subs:
            # Idempotency: skip if already notified for this renewal cycle.
            # "this cycle" = next_payment_at is still in the 3-4 day window
            # and last notification was sent within the last 24h.
            if sub.last_pre_charge_notification_sent_at is not None:
                hours_since_last = (now - sub.last_pre_charge_notification_sent_at).total_seconds() / 3600
                if hours_since_last < 24:
                    self.stdout.write(
                        f"  sub {sub.id}: already notified {hours_since_last:.1f}h ago — skip"
                    )
                    skipped += 1
                    continue

            # Find org owner to use as sender (message comes from coach)
            owner_membership = (
                Membership.objects.filter(
                    organization=sub.organization, role="owner", is_active=True
                )
                .select_related("user")
                .first()
            )
            if not owner_membership:
                self.stdout.write(f"  sub {sub.id}: no owner found — skip")
                skipped += 1
                continue

            plan_name = sub.coach_plan.name if sub.coach_plan else "Sin plan"
            plan_price = sub.coach_plan.price_ars if sub.coach_plan else None
            renewal_date = sub.next_payment_at.strftime("%d/%m/%Y") if sub.next_payment_at else "próximamente"

            price_str = f"${plan_price:,.0f}" if plan_price is not None else ""
            price_part = f" por {price_str} ARS" if price_str else ""

            InternalMessage.objects.create(
                organization=sub.organization,
                sender=owner_membership.user,
                recipient=sub.athlete.user,
                content=(
                    f"\U0001f4b0 Tu suscripción al plan {plan_name} se renovará el "
                    f"{renewal_date}{price_part}. "
                    f"Si querés cancelar o pausar, podés hacerlo desde tu panel antes de esa fecha."
                ),
                alert_type="pre_charge_reminder",
            )

            sub.last_pre_charge_notification_sent_at = now
            sub.save(update_fields=["last_pre_charge_notification_sent_at", "updated_at"])

            logger.info(
                "mp.pre_charge.sent",
                extra={
                    "event_name": "mp.pre_charge.sent",
                    "organization_id": sub.organization_id,
                    "subscription_id": sub.id,
                    "athlete_id": sub.athlete_id,
                    "next_payment_at": sub.next_payment_at.isoformat() if sub.next_payment_at else None,
                    "outcome": "sent",
                },
            )
            self.stdout.write(
                self.style.SUCCESS(f"  sub {sub.id}: notification sent to athlete {sub.athlete_id}")
            )
            sent += 1

        self.stdout.write(f"\nSummary: sent={sent} skipped={skipped}")
