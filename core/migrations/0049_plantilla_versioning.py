from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_security_week1_constraints_and_tenant_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlantillaEntrenamientoVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField()),
                ("estructura", models.JSONField(blank=True, default=dict)),
                ("descripcion", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "plantilla",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versiones",
                        to="core.plantillaentrenamiento",
                    ),
                ),
            ],
            options={
                "ordering": ["-version"],
            },
        ),
        migrations.AddConstraint(
            model_name="plantillaentrenamientoversion",
            constraint=models.UniqueConstraint(fields=("plantilla", "version"), name="unique_version_per_template"),
        ),
        migrations.AddField(
            model_name="entrenamiento",
            name="plantilla_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="entrenamientos",
                to="core.plantillaentrenamientoversion",
            ),
        ),
    ]
