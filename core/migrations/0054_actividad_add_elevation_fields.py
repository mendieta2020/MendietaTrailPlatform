from django.db import migrations, models


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _extract_raw_metric(raw_payload, keys):
    raw_payload = raw_payload or {}
    for key in keys:
        if key in raw_payload:
            value = _safe_float(raw_payload.get(key))
            if value is not None:
                return value
    return None


def backfill_elevation_fields(apps, schema_editor):
    Actividad = apps.get_model("core", "Actividad")
    qs = Actividad.objects.all().only(
        "id",
        "desnivel_positivo",
        "elev_loss_m",
        "elev_gain_m",
        "elev_total_m",
        "datos_brutos",
    )
    for actividad in qs.iterator(chunk_size=500):
        raw = actividad.datos_brutos or {}

        elev_gain = _safe_float(actividad.desnivel_positivo)
        if elev_gain is None:
            elev_gain = _extract_raw_metric(
                raw,
                ("total_elevation_gain", "elev_gain_m", "elevation_gain", "elevation_m"),
            )

        elev_loss_raw = _safe_float(actividad.elev_loss_m)
        if elev_loss_raw is None:
            elev_loss_raw = _extract_raw_metric(
                raw,
                ("total_elevation_loss", "elev_loss_m", "elevation_loss", "elev_loss"),
            )

        elev_gain = max(elev_gain, 0.0) if elev_gain is not None else 0.0
        elev_loss = max(elev_loss_raw, 0.0) if elev_loss_raw is not None else 0.0
        elev_total = elev_gain + elev_loss

        updates = {}
        if actividad.elev_gain_m != elev_gain:
            updates["elev_gain_m"] = elev_gain
        if actividad.elev_total_m != elev_total:
            updates["elev_total_m"] = elev_total
        if actividad.elev_loss_m is None and elev_loss_raw is not None:
            updates["elev_loss_m"] = elev_loss

        if updates:
            Actividad.objects.filter(pk=actividad.pk).update(**updates)


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0053_actividad_canonical_load_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="actividad",
            name="elev_gain_m",
            field=models.FloatField(default=0.0, help_text="Sumatoria de ascenso (metros)."),
        ),
        migrations.AddField(
            model_name="actividad",
            name="elev_total_m",
            field=models.FloatField(default=0.0, help_text="Elevación total (ascenso + descenso)."),
        ),
        migrations.RunPython(backfill_elevation_fields, noop),
    ]
