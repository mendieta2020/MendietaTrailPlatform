from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

from core.models import Actividad, Alumno
from core.utils.logging import safe_extra

logger = logging.getLogger(__name__)


def upsert_actividad(
    *,
    alumno: Alumno,
    usuario,
    source: str,
    source_object_id: str,
    defaults: dict,
) -> tuple[Actividad, bool]:
    """Idempotent upsert por (source, source_object_id) con fallback ante carrera."""
    resolved_usuario = usuario or getattr(alumno, "entrenador", None)

    if not resolved_usuario:
        logger.error(
            "strava.activity.upsert.fail",
            extra=safe_extra(
                {
                    "event_name": "strava.activity.upsert.fail",
                    "reason_code": "missing_usuario",
                    "organization_id": None,
                    "alumno_id": alumno.id if alumno else None,
                }
            ),
        )
        raise ValueError("Cannot upsert Actividad without a valid usuario (tenant).")

    lookup = {
        "source": str(source or ""),
        "source_object_id": str(source_object_id or ""),
    }

    merged = {
        **defaults,
        "alumno": alumno,
        "usuario": resolved_usuario,
        "source": lookup["source"],
        "source_object_id": lookup["source_object_id"],
    }

    with transaction.atomic():
        try:
            obj, created = Actividad.objects.update_or_create(**lookup, defaults=merged)
            return obj, created
        except IntegrityError:
            # Compat: si hay registro legacy por strava_id, lo preferimos y lo "unificamos".
            # Esto cubre casos pre-0041 o data drift donde el UniqueConstraint de strava_id
            # dispara antes que el de (source, source_object_id).
            if lookup["source"] == Actividad.Source.STRAVA and merged.get("strava_id") is not None:
                obj = Actividad.objects.select_for_update().filter(strava_id=merged["strava_id"]).first()
                if obj is not None:
                    for k, v in merged.items():
                        setattr(obj, k, v)
                    obj.save()
                    return obj, False

            # Carrera: otra transacción creó el registro. Re-leemos y aplicamos update.
            obj = Actividad.objects.select_for_update().get(**lookup)
            for k, v in merged.items():
                setattr(obj, k, v)
            obj.save()
            return obj, False
