from django.db import migrations


def forwards(apps, schema_editor):
    """
    Backfill ownership for PlantillaEntrenamiento (multi-tenant).

    Strategy:
    - If a plantilla is referenced by entrenamientos that belong to exactly 1 coach,
      assign that coach as `entrenador`.
    - If it's referenced by entrenamientos from multiple coaches (legacy global plantilla),
      keep one as the "owner" and CLONE the plantilla for the other coaches, re-pointing
      their entrenamientos to the clone. This avoids cross-tenant sharing.
    - If it has no entrenamientos linked, we leave it NULL (orphan/unused). It will not
      appear in coach-scoped APIs; can be handled manually if needed.
    """

    db = schema_editor.connection.alias

    Plantilla = apps.get_model("core", "PlantillaEntrenamiento")
    Entrenamiento = apps.get_model("core", "Entrenamiento")

    # Solo plantillas legacy sin owner
    for tpl in Plantilla.objects.using(db).filter(entrenador__isnull=True).iterator():
        coach_ids = list(
            Entrenamiento.objects.using(db)
            .filter(plantilla_origen_id=tpl.id, alumno__entrenador__isnull=False)
            .values_list("alumno__entrenador_id", flat=True)
            .distinct()
        )
        coach_ids = sorted({cid for cid in coach_ids if cid is not None})

        if len(coach_ids) == 1:
            tpl.entrenador_id = coach_ids[0]
            tpl.save(update_fields=["entrenador"])
            continue

        if len(coach_ids) > 1:
            owner_id = coach_ids[0]
            tpl.entrenador_id = owner_id
            tpl.save(update_fields=["entrenador"])

            # Clonar plantilla para cada coach adicional y re-pointar entrenamientos.
            for coach_id in coach_ids[1:]:
                clone = Plantilla.objects.using(db).create(
                    entrenador_id=coach_id,
                    titulo=tpl.titulo,
                    deporte=tpl.deporte,
                    descripcion_global=tpl.descripcion_global,
                    estructura=tpl.estructura,
                    etiqueta_dificultad=tpl.etiqueta_dificultad,
                )
                Entrenamiento.objects.using(db).filter(
                    plantilla_origen_id=tpl.id,
                    alumno__entrenador_id=coach_id,
                ).update(plantilla_origen_id=clone.id)


def backwards(apps, schema_editor):
    # No intentamos "des-clonar" plantillas (no reversible sin pérdida).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0048_plantillaentrenamiento_entrenador_alter_alumno_email_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

