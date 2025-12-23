from django.db import migrations


def backfill_strava_sport_type(apps, schema_editor):
    Actividad = apps.get_model("core", "Actividad")

    qs = Actividad.objects.filter(source="strava", strava_sport_type="").only("id", "datos_brutos")
    # Best-effort: `datos_brutos` guarda el dict crudo de Strava/stravalib.
    batch = []
    for act in qs.iterator(chunk_size=500):
        raw = act.datos_brutos or {}
        st = raw.get("sport_type") or raw.get("type") or ""
        st_s = str(st or "").strip()
        if not st_s:
            continue
        act.strava_sport_type = st_s
        batch.append(act)
        if len(batch) >= 500:
            Actividad.objects.bulk_update(batch, ["strava_sport_type"])
            batch = []
    if batch:
        Actividad.objects.bulk_update(batch, ["strava_sport_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0043_actividad_strava_sport_type"),
    ]

    operations = [
        migrations.RunPython(backfill_strava_sport_type, migrations.RunPython.noop),
    ]

