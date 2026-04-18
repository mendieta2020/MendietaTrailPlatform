"""
Temporary diagnostic command: reports StravaWebhookEvent status counts
and Redis queue depths. Used for PR-172 hotfix measurement.
Run via: python manage.py queue_audit
"""
from django.core.management.base import BaseCommand
from django.db.models import Count


class Command(BaseCommand):
    help = "Report queue depths and webhook event status counts (PR-172 diagnostic)"

    def handle(self, *args, **options):
        from core.models import StravaWebhookEvent

        self.stdout.write("=== StravaWebhookEvent by status ===")
        # Intentional: system-level operator view, not tenant-scoped.
        counts = (
            StravaWebhookEvent.objects
            .values("status")
            .annotate(n=Count("id"))
            .order_by("status")
        )
        for row in counts:
            self.stdout.write(f"  {row['status']}: {row['n']}")
        total = StravaWebhookEvent.objects.count()
        self.stdout.write(f"  TOTAL: {total}")

        self.stdout.write("\n=== Redis queue depths ===")
        try:
            from django.conf import settings
            import redis as redis_lib
            broker_url = getattr(settings, "CELERY_BROKER_URL", "")
            r = redis_lib.from_url(broker_url)
            queues = [
                "default", "celery",  # "celery" = legacy implicit default; included to detect pre-PR-172 stranded tasks
                "strava_ingest", "suunto_ingest", "analytics_recompute", "notifications",
            ]
            for q in queues:
                depth = r.llen(q)
                self.stdout.write(f"  {q}: {depth}")
        except Exception as exc:
            self.stdout.write(f"  Redis error: {exc}")
