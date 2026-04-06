"""
python manage.py backfill_coaches

Idempotent: creates Coach records for any Membership(role='coach', is_active=True)
that does not yet have one. Safe to run multiple times in production.
"""
from django.core.management.base import BaseCommand

from core.models import Coach, Membership


class Command(BaseCommand):
    help = "Backfill Coach records for existing coach Memberships (idempotent)"

    def handle(self, *args, **options):
        coach_memberships = Membership.objects.filter(
            role="coach", is_active=True
        ).select_related("user", "organization")

        created_count = 0
        skipped_count = 0

        for m in coach_memberships:
            _, created = Coach.objects.get_or_create(
                user=m.user,
                organization=m.organization,
                defaults={"is_active": True},
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count} Coach records. "
                f"Already existed: {skipped_count}."
            )
        )
