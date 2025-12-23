from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0008_daily_activity_agg_and_pmc_history"),
    ]

    operations = [
        migrations.RenameField(
            model_name="alert",
            old_name="payload_json",
            new_name="evidence_json",
        ),
        migrations.AddField(
            model_name="alert",
            name="recommended_action",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="alert",
            name="visto_por_coach",
            field=models.BooleanField(default=False),
        ),
    ]

