from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_athlete_sync_state"),
        ("analytics", "0007_alter_alertarendimiento_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyActivityAgg",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(db_index=True)),
                (
                    "sport",
                    models.CharField(
                        choices=[("RUN", "RUN"), ("TRAIL", "TRAIL"), ("BIKE", "BIKE"), ("WALK", "WALK"), ("OTHER", "OTHER")],
                        db_index=True,
                        max_length=10,
                    ),
                ),
                ("load", models.FloatField(default=0, help_text="Carga/Esfuerzo del día (TSS/Relative Effort proxy)")),
                ("distance_m", models.FloatField(default=0)),
                ("elev_gain_m", models.FloatField(default=0)),
                ("duration_s", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alumno",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_activity_aggs",
                        to="core.alumno",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha"],
                "unique_together": {("alumno", "fecha", "sport")},
            },
        ),
        migrations.CreateModel(
            name="PMCHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField(db_index=True)),
                (
                    "sport",
                    models.CharField(choices=[("ALL", "ALL"), ("RUN", "RUN"), ("BIKE", "BIKE")], db_index=True, max_length=10),
                ),
                ("tss_diario", models.FloatField(default=0)),
                ("ctl", models.FloatField(default=0)),
                ("atl", models.FloatField(default=0)),
                ("tsb", models.FloatField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alumno",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pmc_history",
                        to="core.alumno",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha"],
                "unique_together": {("alumno", "fecha", "sport")},
            },
        ),
        migrations.AddIndex(
            model_name="dailyactivityagg",
            index=models.Index(fields=["alumno", "sport", "-fecha"], name="analytics_d_alumno__f014ff_idx"),
        ),
        migrations.AddIndex(
            model_name="pmchistory",
            index=models.Index(fields=["alumno", "sport", "-fecha"], name="analytics_p_alumno__a0b5c7_idx"),
        ),
    ]

