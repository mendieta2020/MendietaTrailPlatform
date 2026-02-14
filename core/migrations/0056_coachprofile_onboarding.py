from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_rename_core_strava_status_updated_at_idx_core_strava_status_2cb8d4_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoachProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("onboarding_completed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="coach_profile", to=settings.AUTH_USER_MODEL),
                ),
            ],
        ),
    ]
