# Generated manually for PR-141: add repetitions to WorkoutInterval
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0076_workout_delivery_record"),
    ]

    operations = [
        migrations.AddField(
            model_name="workoutinterval",
            name="repetitions",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Number of times this interval is repeated (e.g., 5 for '5 × 1000m').",
            ),
        ),
    ]
