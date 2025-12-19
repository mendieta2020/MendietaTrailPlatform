from __future__ import annotations

from django.db import IntegrityError, transaction

from core.models import Actividad, Alumno


def upsert_actividad(
    *,
    alumno: Alumno,
    usuario,
    source: str,
    source_object_id: str,
    defaults: dict,
) -> tuple[Actividad, bool]:
    """Idempotent upsert por (source, source_object_id) con fallback ante carrera."""
    lookup = {
        "source": str(source or ""),
        "source_object_id": str(source_object_id or ""),
    }

    merged = {
        **defaults,
        "alumno": alumno,
        "usuario": usuario,
        "source": lookup["source"],
        "source_object_id": lookup["source_object_id"],
    }

    with transaction.atomic():
        try:
            obj, created = Actividad.objects.update_or_create(**lookup, defaults=merged)
            return obj, created
        except IntegrityError:
            # Carrera: otra transacción creó el registro. Re-leemos y aplicamos update.
            obj = Actividad.objects.select_for_update().get(**lookup)
            for k, v in merged.items():
                setattr(obj, k, v)
            obj.save()
            return obj, False
