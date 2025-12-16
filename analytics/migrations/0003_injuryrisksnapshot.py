from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("analytics", "0002_alertarendimiento"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InjuryRiskSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(db_index=True)),
                ("risk_level", models.CharField(choices=[("LOW", "LOW"), ("MEDIUM", "MEDIUM"), ("HIGH", "HIGH")], default="LOW", max_length=10)),
                ("risk_score", models.PositiveSmallIntegerField(default=0, help_text="0–100")),
                ("risk_reasons", models.JSONField(blank=True, default=list, help_text="Lista de strings explicables")),
                ("ctl", models.FloatField(default=0)),
                ("atl", models.FloatField(default=0)),
                ("tsb", models.FloatField(default=0)),
                ("version", models.CharField(default="v1", max_length=10)),
                ("computed_at", models.DateTimeField(auto_now=True)),
                (
                    "entrenador",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="injury_risk_snapshots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "alumno",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="injury_risk_snapshots",
                        to="core.alumno",
                    ),
                ),
            ],
            options={
                "verbose_name": "🩺 Injury Risk Snapshot",
                "verbose_name_plural": "🩺 Injury Risk Snapshots",
                "ordering": ["-fecha"],
                "unique_together": {("alumno", "fecha")},
                "indexes": [
                    models.Index(fields=["entrenador", "fecha"], name="analytics_in_entrena_60a63c_idx"),
                    models.Index(fields=["alumno", "-fecha"], name="analytics_in_alumno__e56a57_idx"),
                ],
            },
        ),
    ]

