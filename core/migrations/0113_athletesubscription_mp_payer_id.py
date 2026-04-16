from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0112_reset_mp_plan_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="athletesubscription",
            name="mp_payer_id",
            field=models.CharField(
                blank=True,
                help_text="MP user_id del payer. Obtenido vía GET /users/{payer_id} para reconciliación.",
                max_length=50,
                null=True,
            ),
        ),
    ]
