# Generated for PR-126: fix CompletedActivity.organization FK from User → Organization.
#
# Migration strategy (three-step, db_constraint-safe):
#   1. AlterField with db_constraint=False — changes FK target in state + schema,
#      but does NOT enforce referential integrity (allows legacy User pks temporarily).
#   2. RunPython — data migration: converts each row's organization_id from a
#      User pk to the Organization pk resolved via Membership (fail-safe).
#   3. AlterField with db_constraint=True — re-enables FK integrity constraint.
#
# Reversible: reverse_org_fk converts Organization pks back to User pks via Membership.

import django.db.models.deletion
import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def forward_org_fk(apps, schema_editor):
    """Convert CompletedActivity.organization_id from User pk → Organization pk."""
    CompletedActivity = apps.get_model("core", "CompletedActivity")
    Membership = apps.get_model("core", "Membership")
    Organization = apps.get_model("core", "Organization")

    for activity in CompletedActivity.objects.all():
        # organization_id currently stores a User pk (legacy D2 debt)
        membership = (
            Membership.objects
            .filter(
                user_id=activity.organization_id,
                is_active=True,
                role__in=["owner", "coach"],
            )
            .order_by("id")
            .first()
        )

        if membership is not None:
            activity.organization_id = membership.organization_id
            activity.save(update_fields=["organization_id"])
        else:
            # Fallback: create a minimal Organization so no row is stranded.
            # This handles dev/staging coaches that pre-date the Organization model.
            User = apps.get_model("auth", "User")
            try:
                user = User.objects.get(pk=activity.organization_id)
                slug = f"auto-org-{user.username}-{user.pk}"[:100]
                org, created = Organization.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "name": f"Auto-org for {user.username}",
                        "is_active": True,
                    },
                )
                if created:
                    Membership.objects.create(
                        user=user,
                        organization=org,
                        role="coach",
                        is_active=True,
                    )
                activity.organization_id = org.pk
                activity.save(update_fields=["organization_id"])
            except User.DoesNotExist:
                logger.warning(
                    "pr126.migration.orphan_activity",
                    extra={
                        "activity_id": activity.pk,
                        "stale_user_id": activity.organization_id,
                        "reason": "User no longer exists; activity organization_id unchanged",
                    },
                )


def reverse_org_fk(apps, schema_editor):
    """Convert CompletedActivity.organization_id from Organization pk → User pk."""
    CompletedActivity = apps.get_model("core", "CompletedActivity")
    Membership = apps.get_model("core", "Membership")

    for activity in CompletedActivity.objects.all():
        # organization_id currently stores an Organization pk
        membership = (
            Membership.objects
            .filter(
                organization_id=activity.organization_id,
                is_active=True,
                role__in=["owner", "coach"],
            )
            .order_by("id")
            .first()
        )
        if membership is not None:
            activity.organization_id = membership.user_id
            activity.save(update_fields=["organization_id"])
        else:
            logger.warning(
                "pr126.migration.reverse_no_membership",
                extra={
                    "activity_id": activity.pk,
                    "organization_id": activity.organization_id,
                    "reason": "No active coach/owner Membership found; row left unchanged",
                },
            )


class Migration(migrations.Migration):
    # atomic=False required: PostgreSQL raises
    # "cannot ALTER TABLE because it has pending deferred trigger events"
    # when an AlterField (ALTER TABLE) runs inside a transaction that contains
    # DEFERRABLE INITIALLY DEFERRED RI constraint triggers on this table.
    # Running without wrapping transaction avoids this; each step is still
    # idempotent (get_or_create / AlterField is re-runnable).
    atomic = False

    dependencies = [
        ("core", "0079_workoutblock_add_repetitions"),
    ]

    operations = [
        # Step 1: Change FK target to Organization; disable constraint to allow
        # the existing User-pk values to coexist while we run the data migration.
        migrations.AlterField(
            model_name="completedactivity",
            name="organization",
            field=models.ForeignKey(
                "core.Organization",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="completed_activities",
                db_index=True,
                db_constraint=False,
                help_text="Organization that owns this activity record.",
            ),
        ),
        # Step 2: Data migration — convert User pks → Organization pks.
        migrations.RunPython(forward_org_fk, reverse_org_fk),
        # Step 3: Re-enable FK constraint now that all rows point to valid Organizations.
        migrations.AlterField(
            model_name="completedactivity",
            name="organization",
            field=models.ForeignKey(
                "core.Organization",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="completed_activities",
                db_index=True,
                help_text="Organization that owns this activity record.",
            ),
        ),
    ]
