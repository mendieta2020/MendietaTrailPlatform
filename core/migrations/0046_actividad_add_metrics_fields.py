from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_athlete_sync_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="actividad",
            name="desnivel_positivo",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="actividad",
            name="calories_kcal",
            field=models.FloatField(blank=True, help_text="Calorías (kcal). NULL si faltante.", null=True),
        ),
        migrations.AddField(
            model_name="actividad",
            name="effort",
            field=models.FloatField(
                blank=True,
                help_text="Esfuerzo (Strava relative_effort / suffer_score). NULL si faltante.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="actividad",
            name="elev_loss_m",
            field=models.FloatField(
                blank=True,
                help_text="Sumatoria de descenso (metros). NULL si faltante.",
                null=True,
            ),
        ),
    ]

