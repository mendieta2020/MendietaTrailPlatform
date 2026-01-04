from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0010_rename_analytics_d_alumno__f014ff_idx_analytics_d_alumno__e7515b_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyactivityagg",
            name="calories_kcal",
            field=models.FloatField(default=0.0, help_text="Calorías agregadas del día (kcal). 0 si faltante."),
        ),
    ]

