from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_external_identity_and_link_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="actividad",
            name="strava_sport_type",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
    ]

