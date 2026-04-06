"""
PR-165c: Backfill Coach records for existing Membership(role='coach') rows
that predate the auto-create logic added in TeamJoinView.

Safe to re-run: uses get_or_create.
"""
from django.db import migrations


def backfill_coaches(apps, schema_editor):
    Membership = apps.get_model('core', 'Membership')
    Coach = apps.get_model('core', 'Coach')

    for membership in Membership.objects.filter(role='coach', is_active=True).select_related('user', 'organization'):
        Coach.objects.get_or_create(
            user=membership.user,
            organization=membership.organization,
            defaults={'is_active': True},
        )


def reverse_noop(apps, schema_editor):
    pass  # Non-destructive: leave Coach records in place on reverse


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0109_pr165c_coach_membership_profile_fields'),
    ]

    operations = [
        migrations.RunPython(backfill_coaches, reverse_noop),
    ]
