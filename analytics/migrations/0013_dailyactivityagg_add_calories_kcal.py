from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0012_analyticsrangecache"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    """
                    ALTER TABLE analytics_dailyactivityagg
                    ADD COLUMN IF NOT EXISTS calories_kcal double precision NOT NULL DEFAULT 0;
                    """,
                    """
                    ALTER TABLE analytics_dailyactivityagg
                    DROP COLUMN IF EXISTS calories_kcal;
                    """,
                ),
                migrations.RunSQL(
                    "UPDATE analytics_dailyactivityagg SET calories_kcal = 0 WHERE calories_kcal IS NULL;",
                    "UPDATE analytics_dailyactivityagg SET calories_kcal = 0 WHERE calories_kcal IS NULL;",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="dailyactivityagg",
                    name="calories_kcal",
                    field=models.FloatField(default=0, help_text="Calorías totales del día (kcal). Nunca NULL."),
                ),
            ],
        ),
    ]
