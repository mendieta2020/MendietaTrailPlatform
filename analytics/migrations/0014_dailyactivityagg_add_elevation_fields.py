from django.db import migrations, models
from django.db.models import F


def backfill_daily_elevation(apps, schema_editor):
    DailyActivityAgg = apps.get_model("analytics", "DailyActivityAgg")
    DailyActivityAgg.objects.update(elev_total_m=F("elev_gain_m"))


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0013_dailyactivityagg_add_calories_kcal"),
        ("core", "0054_actividad_add_elevation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyactivityagg",
            name="elev_loss_m",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="dailyactivityagg",
            name="elev_total_m",
            field=models.FloatField(default=0),
        ),
        migrations.RunPython(backfill_daily_elevation, noop),
    ]
