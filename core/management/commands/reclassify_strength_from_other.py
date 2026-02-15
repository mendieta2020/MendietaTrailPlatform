from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_type, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from analytics.models import HistorialFitness
from core.models import Actividad, Alumno, Entrenamiento
from core.utils.logging import safe_extra

logger = logging.getLogger(__name__)


STRENGTH_STRAVA_TYPES_UPPER: frozenset[str] = frozenset({"WEIGHTTRAINING", "WORKOUT", "CROSSFIT"})


def _extract_strava_sport_type_upper(raw: dict | None) -> str:
    """
    Best-effort: Strava puede traer `sport_type` (granular) y/o `type` (legacy).
    Persistimos raw JSON (datos_brutos) pero su shape puede variar.
    """
    raw = raw or {}
    st = raw.get("sport_type") or raw.get("type") or raw.get("workout_type") or ""
    try:
        return str(st).strip().upper()
    except Exception:
        return ""


def _load_score_from_entrenamiento_row(row: dict) -> float:
    """
    Replica la heurística de carga usada por el sistema (best-effort):
    - Si existe `training_load` (implementación nueva), lo prioriza.
    - Si existe `load_final`, lo prioriza (legacy ciencia).
    - Si existe `tss`, lo prioriza.
    - Si no: minutos * (1 + rpe/10) (fallback MVP).
    """
    for key in ("training_load", "load_final", "tss"):
        if key in row:
            v = row.get(key, None)
            if v is not None:
                try:
                    return float(v or 0)
                except Exception:
                    pass

    dur = float(row.get("tiempo_real_min") or 0)
    rpe = float(row.get("rpe") or 0)
    intensity = 1.0 + (max(0.0, min(10.0, rpe)) / 10.0)
    return dur * intensity


def _recompute_historial_fitness_from(alumno_id: int, start_date: date_type) -> dict:
    """
    Recompute incremental de PMC (HistorialFitness) desde `start_date` hasta hoy.

    Idempotente:
    - Borra registros >= start_date y los reconstruye determinísticamente.
    - Mantiene coherencia matemática en días sin carga (tss=0 => decaimiento).
    """
    start_date = date_type.fromisoformat(str(start_date))
    today = timezone.localdate()
    if start_date > today:
        return {"status": "skipped", "reason": "start_date_in_future", "days": 0}

    # Valores base: el último registro existente anterior a start_date (si hay),
    # con decaimiento diario en gaps.
    prev = (
        HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__lt=start_date)
        .order_by("-fecha")
        .values("fecha", "ctl", "atl")
        .first()
    )
    ctl_prev = float((prev or {}).get("ctl") or 0)
    atl_prev = float((prev or {}).get("atl") or 0)
    prev_date = (prev or {}).get("fecha")

    if prev_date is not None:
        d = prev_date + timedelta(days=1)
        while d < start_date:
            # Día sin carga: tss=0
            ctl_prev = ctl_prev + (0.0 - ctl_prev) / 42.0
            atl_prev = atl_prev + (0.0 - atl_prev) / 7.0
            d = d + timedelta(days=1)

    # Borramos rango a recomputar.
    HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__gte=start_date).delete()

    # Traemos entrenamientos en el rango y agrupamos por fecha.
    # Usamos `.values(...)` para ser tolerantes a columnas opcionales (legacy/new).
    def _has_field(field_name: str) -> bool:
        try:
            Entrenamiento._meta.get_field(field_name)
            return True
        except Exception:
            return False

    value_fields: list[str] = ["fecha_asignada", "tiempo_real_min", "rpe"]
    # Campos opcionales si existen en el modelo actual (tolerante a legacy/new)
    for f in ("training_load", "load_final", "tss"):
        if _has_field(f):
            value_fields.append(f)

    entrenos = list(
        Entrenamiento.objects.filter(
            alumno_id=alumno_id,
            completado=True,
            fecha_asignada__range=[start_date, today],
        )
        .values(*value_fields)
        .order_by("fecha_asignada")
    )

    tss_by_day: dict[date_type, float] = defaultdict(float)
    for row in entrenos:
        d = row["fecha_asignada"]
        tss_by_day[d] += float(_load_score_from_entrenamiento_row(row) or 0.0)

    # Reconstrucción día a día (incluye días sin entreno para decaimiento correcto).
    out: list[HistorialFitness] = []
    d = start_date
    while d <= today:
        tss_day = float(tss_by_day.get(d, 0.0) or 0.0)
        ctl_today = ctl_prev + (tss_day - ctl_prev) / 42.0
        atl_today = atl_prev + (tss_day - atl_prev) / 7.0
        tsb_today = ctl_today - atl_today
        out.append(
            HistorialFitness(
                alumno_id=alumno_id,
                fecha=d,
                tss_diario=tss_day,
                ctl=ctl_today,
                atl=atl_today,
                tsb=tsb_today,
            )
        )
        ctl_prev = ctl_today
        atl_prev = atl_today
        d = d + timedelta(days=1)

    HistorialFitness.objects.bulk_create(out, batch_size=500)
    return {"status": "ok", "days": len(out), "start": str(start_date), "end": str(today)}


@dataclass(frozen=True)
class _Change:
    actividad_id: int
    strava_id: int | None
    alumno_id: int | None
    entrenador_id: int | None
    fecha: str
    raw_type: str
    old_tipo_deporte: str
    new_tipo_deporte: str


class Command(BaseCommand):
    help = (
        "Backfill: reclasifica Actividades guardadas como OTHER que en Strava sean "
        "WeightTraining/Workout/Crossfit -> STRENGTH. Opcionalmente recomputa PMC (HistorialFitness)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant_id", type=int, default=None, help="ID del entrenador (tenant). Opcional.")
        parser.add_argument("--alumno_id", type=int, default=None, help="ID del alumno. Opcional.")
        parser.add_argument("--since", type=str, default=None, help="YYYY-MM-DD (opcional): filtra por fecha_inicio >= since.")
        parser.add_argument("--dry-run", action="store_true", help="No escribe cambios; solo muestra conteos/resumen.")

    def handle(self, *args, **options):
        t0 = time.monotonic()

        tenant_id = options.get("tenant_id")
        alumno_id = options.get("alumno_id")
        since_str = options.get("since")
        dry_run = bool(options.get("dry_run"))

        since: date_type | None = None
        if since_str:
            try:
                since = date_type.fromisoformat(str(since_str))
            except ValueError as e:
                raise CommandError("--since debe ser YYYY-MM-DD") from e

        # Base queryset (solo registros con alumno para scoping; evitamos tocar data huérfana).
        scope = Actividad.objects.select_related("alumno").exclude(alumno__isnull=True)

        # Safety multi-tenant: siempre scoping por alumno.entrenador (tenant canónico).
        if tenant_id is not None:
            scope = scope.filter(alumno__entrenador_id=int(tenant_id))
        else:
            # Aún si corre global, evitamos registros sin entrenador para no mezclar tenancy.
            scope = scope.exclude(alumno__entrenador_id__isnull=True)

        if alumno_id is not None:
            scope = scope.filter(alumno_id=int(alumno_id))

        if since is not None:
            # fecha_inicio es DateTimeField; filtramos por fecha local >= since.
            # Usamos __date para ser consistente con "YYYY-MM-DD".
            scope = scope.filter(fecha_inicio__date__gte=since)

        # Solo Strava (fuente esperada para estos tipos).
        scope = scope.filter(source=Actividad.Source.STRAVA)

        # Pre-filtrado best-effort por raw para evitar iterar todo.
        # Nota: en algunos backends/instalaciones el soporte de JSON lookups puede variar;
        # si fallara, hacemos fallback sin este filtro y filtramos en Python.
        raw_q = Q(datos_brutos__sport_type__in=["WeightTraining", "Workout", "Crossfit"]) | Q(
            datos_brutos__type__in=["WeightTraining", "Workout", "Crossfit"]
        )
        qs_with_raw = scope.filter(raw_q)

        # Observabilidad: conteo previo por tipo_deporte dentro del scope (best-effort).
        eligible_counts: dict[str, int] = {}
        try:
            for row in qs_with_raw.values("tipo_deporte").annotate(c=Count("id")):
                eligible_counts[str(row["tipo_deporte"] or "")] = int(row["c"] or 0)
        except Exception:
            eligible_counts = {}

        try:
            candidates = list(qs_with_raw.filter(tipo_deporte="OTHER").order_by("id"))
        except Exception:
            candidates = list(scope.filter(tipo_deporte="OTHER").order_by("id"))

        changes: list[_Change] = []
        affected_min_date_by_alumno: dict[int, date_type] = {}

        for act in candidates:
            raw_type_upper = _extract_strava_sport_type_upper(getattr(act, "datos_brutos", None))
            if raw_type_upper not in STRENGTH_STRAVA_TYPES_UPPER:
                continue

            alumno = getattr(act, "alumno", None)
            entrenador_id = getattr(alumno, "entrenador_id", None) if alumno else None
            fecha_local = act.fecha_inicio.date() if act.fecha_inicio else None

            changes.append(
                _Change(
                    actividad_id=int(act.id),
                    strava_id=int(act.strava_id) if act.strava_id is not None else None,
                    alumno_id=int(act.alumno_id) if act.alumno_id is not None else None,
                    entrenador_id=int(entrenador_id) if entrenador_id is not None else None,
                    fecha=str(fecha_local) if fecha_local else "",
                    raw_type=raw_type_upper,
                    old_tipo_deporte=str(act.tipo_deporte or ""),
                    new_tipo_deporte="STRENGTH",
                )
            )

            if act.alumno_id and fecha_local:
                cur = affected_min_date_by_alumno.get(int(act.alumno_id))
                if cur is None or fecha_local < cur:
                    affected_min_date_by_alumno[int(act.alumno_id)] = fecha_local

        # Output resumen
        self.stdout.write(
            f"eligible_counts={eligible_counts} candidates={len(candidates)} to_change={len(changes)} dry_run={dry_run} tenant_id={tenant_id} alumno_id={alumno_id} since={since_str or ''}"
        )
        for ch in changes[:25]:
            self.stdout.write(
                f"- actividad_id={ch.actividad_id} strava_id={ch.strava_id} alumno_id={ch.alumno_id} tenant_id={ch.entrenador_id} fecha={ch.fecha} raw={ch.raw_type} {ch.old_tipo_deporte}->{ch.new_tipo_deporte}"
            )
        if len(changes) > 25:
            self.stdout.write(f"... ({len(changes) - 25} más)")

        if dry_run or not changes:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "strength.reclassify_from_other.done",
                extra=safe_extra(
                    {
                        "dry_run": dry_run,
                        "tenant_id": tenant_id,
                        "alumno_id": alumno_id,
                        "since": since_str,
                        "candidates": len(candidates),
                        "to_change": len(changes),
                        "duration_ms": duration_ms,
                    }
                ),
            )
            return

        # Ejecución real (idempotente): volvemos a filtrar por ids + estado OTHER antes de escribir.
        touched_actividad_ids = [c.actividad_id for c in changes]

        with transaction.atomic():
            acts_to_update = (
                Actividad.objects.select_for_update()
                .select_related("alumno")
                .filter(id__in=touched_actividad_ids, tipo_deporte="OTHER", source=Actividad.Source.STRAVA)
            )

            updated_acts = 0
            updated_entrenos = 0

            for act in acts_to_update:
                raw_type_upper = _extract_strava_sport_type_upper(getattr(act, "datos_brutos", None))
                if raw_type_upper not in STRENGTH_STRAVA_TYPES_UPPER:
                    continue

                # Extra safety: tenant scoping en runtime (defensa en profundidad).
                if tenant_id is not None and act.alumno and act.alumno.entrenador_id != int(tenant_id):
                    continue

                act.tipo_deporte = "STRENGTH"
                act.save(update_fields=["tipo_deporte"])
                updated_acts += 1

                # Mantener coherencia con Entrenamiento derivado por strava_id (si existe).
                match_id = None
                if act.strava_id is not None:
                    match_id = str(int(act.strava_id))
                elif act.source_object_id:
                    match_id = str(act.source_object_id)

                if match_id and act.alumno_id:
                    updated_entrenos += int(
                        Entrenamiento.objects.filter(alumno_id=act.alumno_id, strava_id=match_id).update(
                            tipo_actividad="STRENGTH"
                        )
                        or 0
                    )

        # Recompute PMC incremental por alumno (fuera de la transacción de updates).
        recomputed = 0
        recompute_days_total = 0
        recompute_results: dict[int, dict] = {}
        for aid, min_date in sorted(affected_min_date_by_alumno.items(), key=lambda x: x[0]):
            # Defensa en profundidad: si el comando estuvo tenant-scoped, el alumno debe pertenecer.
            if tenant_id is not None:
                if not Alumno.objects.filter(id=aid, entrenador_id=int(tenant_id)).exists():
                    continue

            res = _recompute_historial_fitness_from(aid, min_date)
            recompute_results[aid] = res
            if res.get("status") == "ok":
                recomputed += 1
                recompute_days_total += int(res.get("days") or 0)

        duration_ms = int((time.monotonic() - t0) * 1000)
        eligible_counts_after: dict[str, int] = {}
        try:
            qs_after = scope.filter(raw_q)
            for row in qs_after.values("tipo_deporte").annotate(c=Count("id")):
                eligible_counts_after[str(row["tipo_deporte"] or "")] = int(row["c"] or 0)
        except Exception:
            eligible_counts_after = {}

        logger.info(
            "strength.reclassify_from_other.done",
            extra=safe_extra(
                {
                    "dry_run": False,
                    "tenant_id": tenant_id,
                    "alumno_id": alumno_id,
                    "since": since_str,
                    "candidates": len(candidates),
                    "to_change": len(changes),
                    "updated_actividades": updated_acts,
                    "updated_entrenamientos": updated_entrenos,
                    "eligible_counts_before": eligible_counts,
                    "eligible_counts_after": eligible_counts_after,
                    "recomputed_alumnos": recomputed,
                    "recomputed_days": recompute_days_total,
                    "duration_ms": duration_ms,
                }
            ),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK eligible_counts_before={eligible_counts} eligible_counts_after={eligible_counts_after} updated_actividades={updated_acts} updated_entrenamientos={updated_entrenos} recomputed_alumnos={recomputed} duration_ms={duration_ms}"
            )
        )

