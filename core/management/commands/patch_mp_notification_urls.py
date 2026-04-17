"""
Management command: patch_mp_notification_urls

Iterates all CoachPricingPlan records that have an mp_plan_id set and ensures
each has notification_url pointing to our athlete webhook endpoint.

Idempotent — safe to rerun.

Usage:
    python manage.py patch_mp_notification_urls           # apply patches
    python manage.py patch_mp_notification_urls --verify  # show current state, no changes
"""

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Patch notification_url on existing MercadoPago preapproval plans."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verify",
            action="store_true",
            default=False,
            help="Only show current notification_url state; do not modify anything.",
        )

    def handle(self, *args, **options):
        from core.models import CoachPricingPlan, OrgOAuthCredential
        from integrations.mercadopago.subscriptions import (
            update_preapproval_plan_notification_url,
            get_preapproval_plan,
        )

        verify_only = options["verify"]
        backend_url = getattr(settings, "BACKEND_URL", "") or "http://localhost:8000"
        target_url = f"{backend_url}/api/webhooks/mercadopago/athlete/"

        self.stdout.write(f"Target notification_url: {target_url}")
        self.stdout.write(f"Mode: {'verify' if verify_only else 'patch'}\n")

        plans = CoachPricingPlan.objects.filter(
            mp_plan_id__isnull=False, is_active=True
        ).select_related("organization")

        if not plans.exists():
            self.stdout.write("No active plans with mp_plan_id found.")
            return

        counts = {"patched": 0, "skipped": 0, "error": 0}
        self.stdout.write(f"{'plan_id':<30} {'mp_plan_id':<30} {'status'}")
        self.stdout.write("-" * 75)

        for plan in plans:
            cred = OrgOAuthCredential.objects.filter(
                organization=plan.organization, provider="mercadopago"
            ).first()
            if not cred:
                self.stdout.write(
                    f"{str(plan.id):<30} {plan.mp_plan_id:<30} skipped (no MP credential)"
                )
                counts["skipped"] += 1
                continue

            if verify_only:
                try:
                    mp_plan = get_preapproval_plan(cred.access_token, plan.mp_plan_id)
                    current_url = mp_plan.get("notification_url") or "(not set)"
                    self.stdout.write(
                        f"{str(plan.id):<30} {plan.mp_plan_id:<30} current={current_url}"
                    )
                except Exception as exc:
                    self.stdout.write(
                        f"{str(plan.id):<30} {plan.mp_plan_id:<30} error: {exc}"
                    )
                counts["skipped"] += 1
                continue

            # Apply patch
            try:
                update_preapproval_plan_notification_url(
                    cred.access_token, plan.mp_plan_id, target_url
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{str(plan.id):<30} {plan.mp_plan_id:<30} patched"
                    )
                )
                counts["patched"] += 1
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"{str(plan.id):<30} {plan.mp_plan_id:<30} error: {exc}"
                    )
                )
                counts["error"] += 1

        self.stdout.write("\nSummary:")
        self.stdout.write(f"  patched: {counts['patched']}")
        self.stdout.write(f"  skipped: {counts['skipped']}")
        self.stdout.write(f"  error:   {counts['error']}")
