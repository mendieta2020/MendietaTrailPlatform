from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0044_backfill_actividad_strava_sport_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="AthleteSyncState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(db_index=True, default="strava", max_length=20)),
                (
                    "sync_status",
                    models.CharField(
                        choices=[("IDLE", "IDLE"), ("RUNNING", "RUNNING"), ("DONE", "DONE"), ("FAILED", "FAILED")],
                        db_index=True,
                        default="IDLE",
                        max_length=12,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("target_count", models.PositiveIntegerField(default=0)),
                ("processed_count", models.PositiveIntegerField(default=0)),
                ("last_backfill_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("metrics_pending_from", models.DateField(blank=True, db_index=True, null=True)),
                (
                    "metrics_status",
                    models.CharField(
                        choices=[("IDLE", "IDLE"), ("RUNNING", "RUNNING"), ("DONE", "DONE"), ("FAILED", "FAILED")],
                        db_index=True,
                        default="IDLE",
                        max_length=12,
                    ),
                ),
                ("metrics_last_run_at", models.DateTimeField(blank=True, null=True)),
                ("metrics_last_error", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alumno",
                    models.OneToOneField(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sync_state",
                        to="core.alumno",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["provider", "sync_status"], name="core_athletes_provider_5f224e_idx"),
                    models.Index(fields=["provider", "metrics_status"], name="core_athletes_provider_1b04e3_idx"),
                ],
            },
        ),
    ]

