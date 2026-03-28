"""
Migration 0096 — PR-147b: session deep-link fields on InternalMessage

Adds two nullable fields to InternalMessage:
  reference_id   — WorkoutAssignment PK (positive int, no FK to avoid cascade risk)
  reference_date — WorkoutAssignment.scheduled_date (for month-navigation on the frontend)

Both fields are null=True, blank=True so the migration is backward-compatible
and requires no data backfill.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0095_pr147_phone_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="internalmessage",
            name="reference_id",
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="internalmessage",
            name="reference_date",
            field=models.DateField(null=True, blank=True),
        ),
    ]
