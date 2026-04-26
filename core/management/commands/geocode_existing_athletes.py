"""
Management command: geocode_existing_athletes

Geocodes all Athlete records that have a non-empty location_city but null
location_lat. Idempotent: skips athletes that already have coordinates.

Usage:
    python manage.py geocode_existing_athletes
    python manage.py geocode_existing_athletes --dry-run
"""
import logging

from django.core.management.base import BaseCommand

from core.models import Athlete
from core.services_weather import geocode_city_to_coords

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Geocode existing Athlete records with location_city but no lat/lon. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be geocoded without making changes.",
        )
        parser.add_argument(
            "--org-id",
            type=int,
            default=None,
            help="Scope to a single organization ID. Omit to process all orgs (with warning).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        org_id = options["org_id"]

        qs = Athlete.objects.filter(
            location_city__isnull=False,
            location_lat__isnull=True,
        ).exclude(location_city="")

        if org_id:
            qs = qs.filter(organization_id=org_id)
        else:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: --org-id not provided. Processing ALL organizations. "
                    "Use --org-id <id> to scope to a single tenant."
                )
            )

        total = qs.count()
        self.stdout.write(f"Found {total} athlete(s) to geocode.")

        geocoded = 0
        failed = 0

        for athlete in qs.iterator():
            coords = geocode_city_to_coords(athlete.location_city)
            if coords:
                if not dry_run:
                    Athlete.objects.filter(pk=athlete.pk).update(
                        location_lat=coords[0],
                        location_lon=coords[1],
                    )
                self.stdout.write(
                    f"  {'[DRY] ' if dry_run else ''}Geocoded athlete {athlete.pk} "
                    f"({athlete.location_city}) → {coords[0]:.4f}, {coords[1]:.4f}"
                )
                geocoded += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Failed to geocode athlete {athlete.pk} ({athlete.location_city})"
                    )
                )
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Geocoded: {geocoded}, Failed: {failed}, Total: {total}"
                + (" (dry-run, no DB changes)" if dry_run else "")
            )
        )
        logger.info(
            "geocode_existing_athletes.completed",
            extra={
                "event_name": "geocode_existing_athletes.completed",
                "total": total,
                "geocoded": geocoded,
                "failed": failed,
                "dry_run": dry_run,
                "outcome": "success",
            },
        )
