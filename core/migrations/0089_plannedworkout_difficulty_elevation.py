"""
PR-145b: Add difficulty, elevation_gain_min_m, elevation_gain_max_m to PlannedWorkout.

- difficulty: coach-assigned difficulty label (easy/moderate/hard/very_hard)
- elevation_gain_min_m: minimum planned D+ in meters (trail/MTB planning)
- elevation_gain_max_m: maximum planned D+ in meters (trail/MTB planning)

All fields are optional (blank/null) to preserve backward compatibility.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0088_pmc_models_and_activity_biometric_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannedworkout",
            name="difficulty",
            field=models.CharField(
                blank=True,
                choices=[
                    ("easy", "Fácil"),
                    ("moderate", "Moderado"),
                    ("hard", "Difícil"),
                    ("very_hard", "Muy Difícil"),
                ],
                db_index=True,
                default="",
                help_text="Perceived difficulty of the workout prescription.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="plannedworkout",
            name="elevation_gain_min_m",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Minimum planned elevation gain in meters (trail/MTB planning).",
            ),
        ),
        migrations.AddField(
            model_name="plannedworkout",
            name="elevation_gain_max_m",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Maximum planned elevation gain in meters (trail/MTB planning).",
            ),
        ),
    ]
