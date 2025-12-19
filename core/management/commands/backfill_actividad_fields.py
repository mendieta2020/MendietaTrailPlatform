from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from core.models import Actividad
from core.strava_mapper import map_strava_raw_activity_to_actividad_defaults


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill de campos normalizados en Actividad a partir de datos_brutos."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=str, default="strava", help="Fuente (default: strava)")
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Solo actualiza campos vacíos/0 (no pisa valores existentes)",
        )
        parser.add_argument("--limit", type=int, default=0, help="Límite de filas a procesar (0 = sin límite)")
        parser.add_argument("--dry-run", action="store_true", help="No escribe en DB; solo muestra conteos")

    def handle(self, *args, **options):
        source = str(options.get("source") or "strava")
        only_missing = bool(options.get("only_missing"))
        limit = int(options.get("limit") or 0)
        dry_run = bool(options.get("dry_run"))

        qs = Actividad.objects.filter(source=source).exclude(datos_brutos={})

        if only_missing:
            qs = qs.filter(
                Q(nombre="") |
                Q(distancia__lte=0) |
                Q(tiempo_movimiento__lte=0) |
                Q(tipo_deporte="") |
                Q(source_hash="") |
                Q(source_object_id="") |
                Q(strava_id__isnull=True)
            )

        if limit > 0:
            qs = qs.order_by("id")[:limit]

        total = qs.count()
        self.stdout.write(f"backfill_actividad_fields source={source} total={total} only_missing={only_missing} dry_run={dry_run}")
        if total == 0:
            return

        updated = 0
        skipped = 0
        errors = 0

        def _is_missing(field: str, current):
            if field in {"nombre", "tipo_deporte", "source_hash", "source_object_id"}:
                return (current is None) or (str(current) == "")
            if field in {"distancia", "desnivel_positivo"}:
                try:
                    return float(current or 0.0) <= 0.0
                except Exception:
                    return True
            if field in {"tiempo_movimiento"}:
                try:
                    return int(current or 0) <= 0
                except Exception:
                    return True
            if field in {"strava_id"}:
                return current is None
            if field in {"fecha_inicio"}:
                return current is None
            if field in {"ritmo_promedio"}:
                return current is None
            if field in {"mapa_polilinea"}:
                return current is None or str(current) == ""
            if field in {"datos_brutos"}:
                return not bool(current)
            return current is None

        for act in qs.iterator(chunk_size=500):
            raw = act.datos_brutos or {}
            try:
                mapped = map_strava_raw_activity_to_actividad_defaults(raw)
            except Exception as exc:
                errors += 1
                logger.exception("backfill_actividad_fields.mapper_error", extra={"actividad_id": act.id, "source": source})
                self.stderr.write(f"ERR actividad={act.id}: mapper_error {exc}")
                continue

            # mapper devuelve shape tipo map_strava_activity_to_actividad:
            # incluye source/source_object_id. source puede ser redundante; no lo pisamos.
            mapped_source_object_id = str(mapped.get("source_object_id") or "")
            mapped.pop("source", None)
            mapped.pop("source_object_id", None)

            updates: dict = {}
            # Campos "clave" de idempotencia/compat
            if not only_missing or _is_missing("source_object_id", act.source_object_id):
                if mapped_source_object_id:
                    updates["source_object_id"] = mapped_source_object_id
            if not only_missing or _is_missing("strava_id", act.strava_id):
                if mapped.get("strava_id") is not None:
                    updates["strava_id"] = mapped.get("strava_id")

            # Campos de negocio
            for field in [
                "nombre",
                "fecha_inicio",
                "tipo_deporte",
                "distancia",
                "tiempo_movimiento",
                "desnivel_positivo",
                "ritmo_promedio",
                "mapa_polilinea",
                "datos_brutos",
                "source_hash",
            ]:
                if field not in mapped:
                    continue
                if only_missing and not _is_missing(field, getattr(act, field)):
                    continue
                updates[field] = mapped[field]

            if not updates:
                skipped += 1
                continue

            updated += 1
            if dry_run:
                continue

            with transaction.atomic():
                Actividad.objects.filter(pk=act.pk).update(**updates)

        self.stdout.write(self.style.SUCCESS(f"OK updated={updated} skipped={skipped} errors={errors}"))

