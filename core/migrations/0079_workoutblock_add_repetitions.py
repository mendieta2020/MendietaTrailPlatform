# Generated manually for PR-150: add block-level repetitions to WorkoutBlock
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0078_athlete_zone_and_plannedworkout_tss_if"),
    ]

    operations = [
        migrations.AddField(
            model_name="workoutblock",
            name="repetitions",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Number of times this block is repeated as a set "
                    "(e.g., 3 for '3×[400m + 90s rest]'). Minimum 1."
                ),
            ),
        ),
    ]
