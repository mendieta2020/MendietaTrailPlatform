"""
core/management/commands/backfill_sport_types.py — PR-188e Fix 6

Re-classifies CompletedActivity rows with sport='OTHER' and provider='strava'
by running _normalize_strava_sport_type against the raw_payload JSON field.

Usage:
    python manage.py backfill_sport_types           # live run
    python manage.py backfill_sport_types --dry-run # preview only
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill sport='OTHER' Strava activities using raw_payload sport_type."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        from core.models import CompletedActivity
        from integrations.strava.normalizer import (
            _normalize_strava_sport_type,
            extract_strava_sport_type,
        )

        dry_run = options["dry_run"]
        qs = CompletedActivity.objects.filter(
            sport="OTHER",
            provider=CompletedActivity.Provider.STRAVA,
        )

        total = qs.count()
        updated = 0
        skipped = 0

        self.stdout.write(
            f"Found {total} OTHER/strava activities to inspect."
        )

        for activity in qs.iterator(chunk_size=200):
            raw = activity.raw_payload or {}
            raw_type = extract_strava_sport_type(raw)
            if not raw_type:
                skipped += 1
                continue
            new_sport = _normalize_strava_sport_type(raw)
            if new_sport == "OTHER":
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"  [dry-run] id={activity.pk} '{raw_type}' → {new_sport}"
                )
                updated += 1
            else:
                CompletedActivity.objects.filter(pk=activity.pk).update(sport=new_sport)
                updated += 1
                logger.info(
                    "backfill_sport_types.updated",
                    extra={
                        "event_name": "backfill_sport_types.updated",
                        "activity_id": activity.pk,
                        "old_sport": "OTHER",
                        "new_sport": new_sport,
                        "raw_type": raw_type,
                    },
                )

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done — updated {updated}, skipped {skipped} (still OTHER or no raw type)."
            )
        )
