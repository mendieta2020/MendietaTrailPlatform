from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db import transaction
from django.db.models import F
import openai
import logging
import traceback
import random
import time

from .utils.logging import safe_extra

from .models import (
    Entrenamiento,
    Alumno,
    InscripcionCarrera,
    Actividad,
    StravaWebhookEvent,
    StravaImportLog,
    StravaActivitySyncState,
    ExternalIdentity,
)
from analytics.models import HistorialFitness 

# Logger profesional para monitoreo (Sentry/Datadog ready)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Linking / draining helpers
# ------------------------------------------------------------------------------

@shared_task
def drain_strava_events_for_athlete(*, provider: str = "strava", owner_id: int, limit: int = 250):
    """
    Re-encola eventos en estado LINK_REQUIRED para un atleta externo.

    Se usa al completar linking (OAuth/admin) para evitar pérdida de datos:
    - selecciona eventos pendientes
    - los marca QUEUED y los re-encola
    """
    owner_key = str(int(owner_id))
    qs = (
        StravaWebhookEvent.objects.filter(provider=provider, owner_id=int(owner_id), status=StravaWebhookEvent.Status.LINK_REQUIRED)
        .order_by("received_at")
        .values_list("id", flat=True)[: int(limit)]
    )
    ids = list(qs)
    if not ids:
        return 0

    # Marcar queued en bulk para que sea visible en UI/ops.
    StravaWebhookEvent.objects.filter(id__in=ids).update(status=StravaWebhookEvent.Status.QUEUED, last_error="", error_message="")

    # Spread leve para evitar thundering herd (el lock por actividad ya cubre concurrencia).
    for i, event_id in enumerate(ids):
        process_strava_event.apply_async(args=[event_id], countdown=min(i, 15))
    logger.info("strava.drain.link_required.requeued", extra={"provider": provider, "owner_id": owner_key, "count": len(ids)})
    return len(ids)

# Importación segura de métricas (Fail-safe architecture)
try:
    from .metrics import (
        calcular_trimp, 
        calcular_tss_estimado, # Legacy support
        calcular_load_rpe, 
        determinar_carga_final,
        # Fase 4: Trail Science
        calcular_pendiente,
        calcular_gap_minetti,
        calcular_tss_gap,
        calcular_tss_power,
        velocidad_a_pace
    )
except ImportError:
    logger.error("Error importando métricas científicas. El sistema usará valores por defecto.")
    pass

# --- UTILIDADES INTERNAS (ROBUST DATA EXTRACTION) ---

def safe_duration_minutes(obj_duration):
    """Extrae minutos de cualquier objeto de tiempo de forma segura."""
    if not obj_duration: return 0
    try:
        if hasattr(obj_duration, 'total_seconds'): return int(obj_duration.total_seconds() / 60)
        if hasattr(obj_duration, 'seconds'): return int(obj_duration.seconds / 60)
        return int(float(obj_duration) / 60)
    except: return 0

def safe_float_value(obj_metric):
    """Extrae float de objetos con unidades (pint library compat)."""
    if not obj_metric: return 0.0
    try:
        if hasattr(obj_metric, 'magnitude'): return float(obj_metric.magnitude)
        return float(obj_metric)
    except: return 0.0

def map_strava_type_internal(strava_type):
    """Mapeo estándar de tipos de actividad Strava -> Mendieta."""
    st = str(strava_type).upper()
    if 'RUN' in st: return 'RUN'
    if 'RIDE' in st or 'EBIKE' in st: return 'CYCLING'
    if 'SWIM' in st: return 'SWIMMING'
    if 'WEIGHT' in st or 'CROSSFIT' in st: return 'STRENGTH'
    if 'HIKE' in st or 'WALK' in st: return 'TRAIL'
    if 'VIRTUALRIDE' in st: return 'INDOOR_BIKE'
    return 'OTHER'

# ==============================================================================
#  TAREA 1: MOTOR DE CÁLCULO (CIENCIA TRAIL V2)
# ==============================================================================
@shared_task
def procesar_metricas_entrenamiento(entrenamiento_id):
    try:
        entreno = Entrenamiento.objects.select_related('alumno').get(pk=entrenamiento_id)
        alumno = entreno.alumno
        logger.info(f"🧮 [CIENCIA TRAIL] Procesando: {entreno.titulo} (ID: {entreno.id})")

        tiempo_min = entreno.tiempo_real_min
        distancia_km = entreno.distancia_real_km
        desnivel_m = entreno.desnivel_real_m or 0
        
        if not tiempo_min or tiempo_min <= 0:
            logger.warning(f"⚠️ [SKIP] ID {entreno.id}: Sin tiempo registrado.")
            return "SKIPPED"

        # --- A. CÁLCULOS FISIOLÓGICOS BÁSICOS ---
        # 1. TRIMP (Carga Cardíaca)
        if entreno.frecuencia_cardiaca_promedio:
            entreno.trimp = calcular_trimp(
                tiempo_min, entreno.frecuencia_cardiaca_promedio, 
                alumno.fcm, alumno.fcreposo
            )

        # --- B. CÁLCULOS ESPECÍFICOS (POTENCIA vs GAP) ---
        tss_calculado = 0
        if_calculado = 0

        # Caso 1: Hay Potencia Real (Prioridad Absoluta - Stryd/Garmin)
        if entreno.potencia_promedio:
            tss_calculado, if_calculado = calcular_tss_power(
                tiempo_min, entreno.potencia_promedio, alumno.ftp
            )
            entreno.kilojoules = int((entreno.potencia_promedio * tiempo_min * 60) / 1000)
            logger.info(f"   ⚡ Potencia: {entreno.potencia_promedio}w | TSS Power: {tss_calculado}")
        
        # Caso 2: Trail Running sin Potencia (Usamos GAP + Minetti)
        elif distancia_km and distancia_km > 0:
            # 1. Calcular variables del terreno
            ritmo_real_seg_km = (tiempo_min * 60) / distancia_km
            pendiente = calcular_pendiente(distancia_km * 1000, desnivel_m)
            
            # 2. Aplicar MINETTI (Aplanar la montaña)
            gap_seg_km = calcular_gap_minetti(ritmo_real_seg_km, pendiente)
            
            # 3. Obtener Umbral del Alumno (VAM/UANAE)
            umbral_velocidad = alumno.velocidad_uanae or alumno.vam_actual
            if umbral_velocidad > 0:
                umbral_ritmo = velocidad_a_pace(umbral_velocidad)
            else:
                umbral_ritmo = 240 # Placeholder: 4:00 min/km

            # 4. Calcular rTSS basado en GAP
            tss_calculado, if_calculado = calcular_tss_gap(tiempo_min, gap_seg_km, umbral_ritmo)
            
            logger.info(f"   ⛰️ Trail Data: Pendiente {pendiente:.1f}% | GAP {int(gap_seg_km)}s/km | rTSS {tss_calculado}")

        # --- C. GUARDADO INTELIGENTE ---
        if tss_calculado > 0:
            entreno.tss = tss_calculado
            entreno.intensity_factor = if_calculado

        rpe_load = calcular_load_rpe(tiempo_min, entreno.rpe)
        entreno.load_final = determinar_carga_final(entreno.tss, entreno.tss, entreno.trimp, rpe_load)
        
        # --- D. ACTUALIZACIÓN DE CARRERA (EVENTO FINALIZADO) ---
        # Si este entreno es el día de una carrera inscrita, cerramos el ciclo.
        try:
            carrera_match = InscripcionCarrera.objects.filter(
                alumno=alumno, 
                carrera__fecha__range=[
                    entreno.fecha_asignada - timezone.timedelta(days=1), 
                    entreno.fecha_asignada + timezone.timedelta(days=1)
                ]
            ).first()
            
            if carrera_match:
                carrera_match.estado = 'FINALIZADO'
                carrera_match.tiempo_oficial = timezone.timedelta(minutes=tiempo_min)
                # Aquí podríamos guardar feedback automático en la inscripción
                carrera_match.save()
                logger.info(f"   🏅 Carrera '{carrera_match.carrera.nombre}' finalizada automáticamente.")
        except Exception as e:
            logger.error(f"Error actualizando carrera: {e}")

        entreno.save()
        print(f"✅ [RESULTADO] Carga Final: {entreno.load_final:.1f}")
        return "OK"

    except Exception as e:
        print(f"❌ [ERROR CIENCIA]: {e}")
        traceback.print_exc()
        return "FAIL"

# ==============================================================================
#  TAREA 2: ENTRENADOR IA (LLM - CEREBRO CUALITATIVO)
# ==============================================================================
@shared_task
def generar_feedback_ia(entrenamiento_id):
    if not settings.OPENAI_API_KEY: return "SKIPPED"
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    try:
        entreno = Entrenamiento.objects.select_related('alumno').get(pk=entrenamiento_id)
        fitness = HistorialFitness.objects.filter(alumno=entreno.alumno).order_by('-fecha').first()
        tsb = fitness.tsb if fitness else 0
        
        # Contexto Trail Avanzado
        contexto_trail = ""
        km_esfuerzo = entreno.distancia_real_km
        if entreno.desnivel_real_m and entreno.desnivel_real_m > 0:
            km_esfuerzo += (entreno.desnivel_real_m / 100) # Regla ITRA
            contexto_trail = f"Desnivel: +{entreno.desnivel_real_m}m. Km-Esfuerzo: {km_esfuerzo:.1f}km."

        prompt = f"""
        Actúa como entrenador de Trail Running experto. Analiza para {entreno.alumno.nombre}:
        - Sesión: {entreno.titulo} ({entreno.distancia_real_km}km en {entreno.tiempo_real_min}min).
        - {contexto_trail}
        - Carga (TSS): {entreno.tss} | Fatiga (TSB): {tsb:.1f}
        
        Dame un feedback de 1 frase motivadora y 1 consejo técnico específico (nutrición/bajada/subida). Usa emojis.
        """
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        entreno.feedback_ia = response.choices[0].message.content
        entreno.save()
        return "OK IA"
    except Exception as e:
        print(f"❌ [ERROR IA]: {e}")
        return "FAIL IA"

# ==============================================================================
#  TAREA 3: INGESTA DE DATOS (STRAVA ROBUSTO: idempotente + dedupe + auditoría)
# ==============================================================================
def _strava_retry_delays_seconds():
    # Configurable en settings.py si querés ajustar agresividad.
    return getattr(settings, "STRAVA_WEBHOOK_RETRY_DELAYS", [30, 120, 300, 900, 3600])


def _retry_countdown_with_jitter(retry_index: int) -> int:
    delays = _strava_retry_delays_seconds()
    base = delays[min(retry_index, len(delays) - 1)]
    # jitter 0–20% para evitar thundering herd
    jitter = int(base * random.uniform(0.0, 0.2))
    return base + jitter


def _supported_strava_activity_type(strava_type: str) -> bool:
    st = (strava_type or "").upper()
    # Tipos soportados (estricto). Ajustable si querés más deportes.
    return st in {"RUN", "TRAILRUN", "VIRTUALRUN", "WORKOUT"}


def _normalize_strava_activity(activity) -> dict:
    """
    Convierte objeto stravalib Activity a dict estable (para tests/auditoría).
    """
    # Raw JSON (best-effort)
    raw = {}
    try:
        if hasattr(activity, "to_dict"):
            raw = activity.to_dict()
        elif hasattr(activity, "model_dump"):
            raw = activity.model_dump()
    except Exception:
        raw = {}

    athlete_id = None
    try:
        athlete_id = int(getattr(getattr(activity, "athlete", None), "id", None))
    except Exception:
        athlete_id = None

    start_dt = getattr(activity, "start_date_local", None) or getattr(activity, "start_date", None)
    moving_time_s = 0
    try:
        mt = getattr(activity, "moving_time", None)
        if mt is not None:
            if hasattr(mt, "total_seconds"):
                moving_time_s = int(mt.total_seconds())
            elif hasattr(mt, "seconds"):
                moving_time_s = int(mt.seconds)
            else:
                moving_time_s = int(mt)
    except Exception:
        moving_time_s = 0

    elapsed_time_s = 0
    try:
        et = getattr(activity, "elapsed_time", None)
        if et is not None:
            if hasattr(et, "total_seconds"):
                elapsed_time_s = int(et.total_seconds())
            elif hasattr(et, "seconds"):
                elapsed_time_s = int(et.seconds)
            else:
                elapsed_time_s = int(et)
    except Exception:
        elapsed_time_s = 0

    distance_m = safe_float_value(getattr(activity, "distance", None))
    elev_m = safe_float_value(getattr(activity, "total_elevation_gain", None))

    avg_hr = getattr(activity, "average_heartrate", None)
    max_hr = getattr(activity, "max_heartrate", None)
    avg_watts = getattr(activity, "average_watts", None)

    polyline = None
    try:
        polyline = getattr(getattr(activity, "map", None), "summary_polyline", None)
    except Exception:
        polyline = None

    return {
        "id": int(getattr(activity, "id")),
        "athlete_id": athlete_id,
        "name": str(getattr(activity, "name", "") or ""),
        "type": str(getattr(activity, "type", "") or ""),
        "start_date_local": start_dt,
        "moving_time_s": int(moving_time_s),
        "elapsed_time_s": int(elapsed_time_s),
        "distance_m": float(distance_m or 0.0),
        "elevation_m": float(elev_m or 0.0),
        "avg_hr": float(avg_hr) if avg_hr is not None else None,
        "max_hr": float(max_hr) if max_hr is not None else None,
        "avg_watts": float(avg_watts) if avg_watts is not None else None,
        "polyline": polyline,
        "raw": raw,
    }


def _classify_transient_strava_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "502" in msg or "503" in msg or "504" in msg or "server error" in msg or "bad gateway" in msg:
        return "server_error"
    if "connection" in msg or "temporar" in msg:
        return "network"
    if "401" in msg or "unauthorized" in msg:
        return "unauthorized"
    return ""


class StravaTransientError(Exception):
    """Errores transitorios (429/5xx/timeouts/network) -> retry con backoff."""


def _strava_activity_lock_ttl_seconds() -> int:
    return int(getattr(settings, "STRAVA_ACTIVITY_LOCK_TTL_SECONDS", 15 * 60))


def _log_strava_ingest(
    *,
    msg: str,
    event_uid: str,
    correlation_id=None,
    athlete_id: int | None,
    activity_id: int | None,
    status: str,
    reason: str = "",
    attempt: int = 0,
    duration_ms: int | None = None,
    metric_processed: int = 0,
    metric_ignored: int = 0,
    metric_failed: int = 0,
):
    extra = {
        "event_uid": event_uid,
        "correlation_id": str(correlation_id) if correlation_id else "",
        "athlete_id": athlete_id,
        "activity_id": activity_id,
        "status": status,
        "reason": reason,
        "attempt": attempt,
    }
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    # Métricas mínimas (para agregación por logs)
    if metric_processed:
        extra["metric_processed"] = int(metric_processed)
    if metric_ignored:
        extra["metric_ignored"] = int(metric_ignored)
    if metric_failed:
        extra["metric_failed"] = int(metric_failed)
    logger.info(msg, extra=extra)


def _build_strava_activity_upserted_extra(
    *,
    alumno_id: int,
    source: str,
    source_object_id: str,
    upsert_created: bool,
    payload_sanitized: bool,
) -> dict:
    # Keep keys LogRecord-safe (no reserved names like `created`, `name`, `message`, etc.)
    return {
        "alumno_id": int(alumno_id),
        "source": str(source),
        "source_object_id": str(source_object_id),
        "upsert_created": bool(upsert_created),
        "payload_sanitized": bool(payload_sanitized),
    }


def _log_strava_activity_upserted(
    *,
    alumno_id: int,
    source: str,
    source_object_id: str,
    upsert_created: bool,
    payload_sanitized: bool,
):
    logger.info(
        "strava.activity.upserted",
        extra=safe_extra(
            _build_strava_activity_upserted_extra(
                alumno_id=alumno_id,
                source=source,
                source_object_id=source_object_id,
                upsert_created=upsert_created,
                payload_sanitized=payload_sanitized,
            )
        ),
    )


def _map_strava_type_to_core(tipo: str) -> str:
    """
    Strava -> choices TIPO_ACTIVIDAD de Entrenamiento.
    """
    st = (tipo or "").upper()
    if st in {"RUN", "TRAILRUN", "VIRTUALRUN"}:
        return "RUN"
    return "OTHER"


@shared_task(
    bind=True,
    max_retries=8,
    autoretry_for=(StravaTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=3600,
)
def process_strava_event(self, event_id: int):
    """
    Wrapper de robustez de ciclo de vida.

    WHY:
    - Un crash inesperado (excepción no controlada) podía dejar el evento en PROCESSING con processed_at=NULL
      y el lock de StravaActivitySyncState tomado indefinidamente.
    - Los errores definitivos deben cerrar el ciclo (processed_at=now) y liberar lock.
    - Los errores transitorios (StravaTransientError) NO deben cerrar processed_at porque Celery reintenta.
    """
    attempt_no = int(getattr(self.request, "retries", 0)) + 1
    t0 = time.monotonic()

    def _truncate_err(msg: str, limit: int = 512) -> str:
        return (msg or "")[:limit]

    try:
        return _process_strava_event_body(self, event_id=event_id, attempt_no=attempt_no, t0=t0)
    except StravaTransientError:
        # Mantener comportamiento existente: retry transitorio -> NO cerrar el evento.
        raise
    except Exception as exc:
        # Crash inesperado: cerrar evento y liberar lock (best-effort), sin romper idempotencia.
        now = timezone.now()
        last_error = _truncate_err(str(exc), 512)
        error_message = _truncate_err(f"{exc.__class__.__name__}: {str(exc)}", 1024)

        # Best-effort: obtener contexto mínimo sin leer payloads (evitar datos sensibles).
        ctx = (
            StravaWebhookEvent.objects.filter(pk=event_id)
            .values("event_uid", "provider", "owner_id", "object_id", "status")
            .first()
        ) or {}
        event_uid = ctx.get("event_uid", "") or ""
        provider = ctx.get("provider", "") or ""
        owner_id = ctx.get("owner_id", None)
        object_id = ctx.get("object_id", None)
        status = ctx.get("status", None)

        logger.exception(
            "strava.process_event.unhandled_exception",
            extra=safe_extra(
                {
                    "event_uid": event_uid,
                    "event_id": event_id,
                    "owner_id": owner_id,
                    "object_id": object_id,
                    "status": status,
                }
            ),
        )

        # No romper idempotencia: si ya está PROCESSED/IGNORED/DISCARDED, no lo tocamos.
        StravaWebhookEvent.objects.filter(pk=event_id).exclude(
            status__in=[
                StravaWebhookEvent.Status.PROCESSED,
                StravaWebhookEvent.Status.IGNORED,
                StravaWebhookEvent.Status.DISCARDED,
            ]
        ).update(
            status=StravaWebhookEvent.Status.FAILED,
            last_error=last_error,
            error_message=error_message,
            processed_at=now,
        )

        # Liberar lock por actividad (best-effort).
        try:
            if provider and object_id is not None:
                StravaActivitySyncState.objects.filter(
                    provider=provider, strava_activity_id=int(object_id)
                ).update(
                    status=StravaActivitySyncState.Status.FAILED,
                    last_error=last_error,
                    locked_at=None,
                    locked_by_event_uid="",
                    last_attempt_at=now,
                )
        except Exception:
            logger.exception(
                "strava.process_event.unhandled_exception.unlock_failed",
                extra=safe_extra({"event_uid": event_uid, "event_id": event_id, "owner_id": owner_id, "object_id": object_id}),
            )
        raise


def _process_strava_event_body(self, *, event_id: int, attempt_no: int, t0: float):
    """
    Procesa un StravaWebhookEvent:
    - idempotente (event_uid único)
    - dedupe (Actividad/Entrenamiento)
    - retries con backoff+jitter para 429/5xx/timeouts
    - auditoría en StravaImportLog
    """
    from .actividad_upsert import upsert_actividad
    from .services import obtener_cliente_strava_para_alumno
    from .strava_mapper import (
        map_strava_activity_to_actividad,
        normalize_strava_activity,
        supported_strava_activity_type,
    )

    with transaction.atomic():
        event = StravaWebhookEvent.objects.select_for_update().get(pk=event_id)
        event_uid = event.event_uid
        correlation_id = event.correlation_id
        event.last_attempt_at = timezone.now()

        # Idempotencia fuerte: si ya está procesado/ignorado, no hacemos nada.
        if event.status in {
            StravaWebhookEvent.Status.PROCESSED,
            StravaWebhookEvent.Status.IGNORED,
            StravaWebhookEvent.Status.DISCARDED,
        }:
            return f"NOOP: {event.status}"

        # Si falló antes pero sigue en cola, permitimos reintento.
        event.status = StravaWebhookEvent.Status.PROCESSING
        event.attempts = F("attempts") + 1
        event.last_error = ""
        event.save(update_fields=["status", "attempts", "last_error", "last_attempt_at"])

    _log_strava_ingest(
        msg="strava.process_event.start",
        event_uid=event_uid,
        correlation_id=correlation_id,
        athlete_id=int(event.owner_id) if event.owner_id is not None else None,
        activity_id=int(event.object_id) if event.object_id is not None else None,
        status="processing",
        reason="start",
        attempt=attempt_no,
    )

    # Validación básica del evento
    if event.object_type != "activity":
        StravaWebhookEvent.objects.filter(pk=event.pk).update(
            status=StravaWebhookEvent.Status.IGNORED,
            discard_reason="non_activity_event",
            processed_at=timezone.now(),
        )
        return "IGNORED: non-activity"

    if event.aspect_type == "delete":
        StravaWebhookEvent.objects.filter(pk=event.pk).update(
            status=StravaWebhookEvent.Status.IGNORED,
            discard_reason="delete_event_ignored",
            processed_at=timezone.now(),
        )
        return "IGNORED: delete"

    # Lock lógico por actividad (evita pipelines simultáneos para la misma activity_id).
    lock_ttl_s = _strava_activity_lock_ttl_seconds()
    now = timezone.now()
    with transaction.atomic():
        state, created = StravaActivitySyncState.objects.select_for_update().get_or_create(
            provider=event.provider,
            strava_activity_id=int(event.object_id),
            defaults={
                "athlete_id": int(event.owner_id) if event.owner_id is not None else None,
                "status": StravaActivitySyncState.Status.RUNNING,
                "locked_at": now,
                "locked_by_event_uid": event_uid,
                "attempts": 1,
                "last_attempt_at": now,
                "last_error": "",
                "discard_reason": "",
            },
        )
        if not created:
            in_progress = (
                state.status == StravaActivitySyncState.Status.RUNNING
                and state.locked_at is not None
                and (now - state.locked_at).total_seconds() < lock_ttl_s
                and state.locked_by_event_uid
                and state.locked_by_event_uid != event_uid
            )
            if in_progress:
                StravaImportLog.objects.create(
                    event_id=event.pk,
                    alumno=None,
                    actividad=None,
                    strava_activity_id=event.object_id,
                    attempt=attempt_no,
                    status=StravaImportLog.Status.DISCARDED,
                    reason="activity_lock_in_progress",
                    details={"locked_by_event_uid": state.locked_by_event_uid, "locked_at": str(state.locked_at)},
                )
                StravaWebhookEvent.objects.filter(pk=event.pk).update(
                    status=StravaWebhookEvent.Status.DISCARDED,
                    discard_reason="activity_lock_in_progress",
                    processed_at=timezone.now(),
                )
                duration_ms = int((time.monotonic() - t0) * 1000)
                _log_strava_ingest(
                    msg="strava.process_event.discarded",
                    event_uid=event_uid,
                    athlete_id=int(event.owner_id),
                    activity_id=int(event.object_id),
                    status="discarded",
                    reason="activity_lock_in_progress",
                    attempt=attempt_no,
                    duration_ms=duration_ms,
                )
                return "DISCARDED: activity_lock_in_progress"

            # Re-entrante (retry) o lock expirado: tomamos el lock.
            StravaActivitySyncState.objects.filter(pk=state.pk).update(
                athlete_id=int(event.owner_id) if event.owner_id is not None else state.athlete_id,
                status=StravaActivitySyncState.Status.RUNNING,
                locked_at=now,
                locked_by_event_uid=event_uid,
                attempts=F("attempts") + 1,
                last_attempt_at=now,
            )

    # ------------------------------------------------------------------------------
    # Canonical identity resolution (multi-provider, future-proof)
    # ------------------------------------------------------------------------------
    alumno = None
    identity = None
    owner_key = str(int(event.owner_id)) if event.owner_id is not None else ""

    if owner_key:
        # Preferimos la identidad canónica (ExternalIdentity) para desacoplar Strava->Alumno.
        identity = (
            ExternalIdentity.objects.select_related("alumno")
            .filter(provider=event.provider, external_user_id=owner_key)
            .first()
        )
        if identity and identity.alumno_id:
            alumno = identity.alumno
        else:
            # Fallback de compat: viejos registros linkeados por `Alumno.strava_athlete_id`.
            alumno = (
                Alumno.objects.filter(strava_athlete_id=owner_key)
                .select_related("entrenador", "equipo")
                .first()
            )
            if alumno:
                # Backfill automático: si existía Alumno pero no ExternalIdentity, lo creamos/linkeamos.
                defaults = {
                    "status": ExternalIdentity.Status.LINKED,
                    "alumno": alumno,
                    "linked_at": timezone.now(),
                }
                try:
                    identity, created = ExternalIdentity.objects.get_or_create(
                        provider=event.provider,
                        external_user_id=owner_key,
                        defaults=defaults,
                    )
                    if not created and identity.alumno_id != alumno.id:
                        # Caso raro: ya existía identidad, la re-vinculamos (auditable por DB constraints).
                        ExternalIdentity.objects.filter(pk=identity.pk).update(
                            alumno=alumno,
                            status=ExternalIdentity.Status.LINKED,
                            linked_at=timezone.now(),
                        )
                except Exception:
                    logger.exception(
                        "strava.identity.backfill_failed",
                        extra={"provider": event.provider, "external_user_id": owner_key, "event_uid": event_uid},
                    )
            else:
                # Seed defensivo: que exista la identidad UNLINKED aunque no haya Alumno todavía.
                if identity is None:
                    try:
                        identity, _ = ExternalIdentity.objects.get_or_create(
                            provider=event.provider,
                            external_user_id=owner_key,
                            defaults={"status": ExternalIdentity.Status.UNLINKED},
                        )
                    except Exception:
                        logger.exception(
                            "strava.identity.seed_failed",
                            extra={"provider": event.provider, "external_user_id": owner_key, "event_uid": event_uid},
                        )

    if not alumno:
        instruction = (
            "Webhook recibido para atleta aún no vinculado. "
            "Acción: el atleta debe conectar Strava (OAuth) o un admin debe vincular el athlete_id al Alumno. "
            "Este evento quedará pendiente y se reprocesará automáticamente al vincular."
        )
        StravaImportLog.objects.create(
            event_id=event.pk,
            alumno=None,
            actividad=None,
            strava_activity_id=event.object_id,
            attempt=attempt_no,
            status=StravaImportLog.Status.DEFERRED,
            reason="link_required",
            details={"owner_id": event.owner_id, "external_user_id": owner_key, "provider": event.provider},
        )
        StravaWebhookEvent.objects.filter(pk=event.pk).update(
            status=StravaWebhookEvent.Status.LINK_REQUIRED,
            discard_reason="link_required",
            error_message=instruction,
            processed_at=None,
        )
        StravaActivitySyncState.objects.filter(provider=event.provider, strava_activity_id=int(event.object_id)).update(
            status=StravaActivitySyncState.Status.BLOCKED,
            discard_reason="link_required",
            locked_at=None,
            locked_by_event_uid="",
            last_error="",
            last_attempt_at=timezone.now(),
        )
        return "DEFERRED: link_required"

    client = obtener_cliente_strava_para_alumno(alumno)
    if not client:
        instruction = (
            "Strava no conectado para este atleta. "
            "Acción: el atleta debe conectar Strava vía /accounts/ (Allauth) "
            "o el entrenador debe conectar la integración si el setup es legacy."
        )
        StravaImportLog.objects.create(
            event_id=event.pk,
            alumno=alumno,
            actividad=None,
            strava_activity_id=event.object_id,
            attempt=attempt_no,
            status=StravaImportLog.Status.FAILED,
            reason="missing_strava_auth",
            details={"coach_id": alumno.entrenador_id, "alumno_user_id": alumno.usuario_id},
        )
        StravaWebhookEvent.objects.filter(pk=event.pk).update(
            status=StravaWebhookEvent.Status.FAILED,
            discard_reason="missing_strava_auth",
            last_error="missing_strava_auth",
            error_message=instruction,
            processed_at=timezone.now(),
        )
        StravaActivitySyncState.objects.filter(provider=event.provider, strava_activity_id=int(event.object_id)).update(
            status=StravaActivitySyncState.Status.FAILED,
            last_error="missing_strava_auth",
            discard_reason="missing_strava_auth",
            locked_at=None,
            locked_by_event_uid="",
            last_attempt_at=timezone.now(),
        )
        return "FAIL: no strava auth"

    # Fetch activity desde Strava (con refresh forzado ante 401)
    activity = None
    fetch_error = None
    try:
        activity_obj = client.get_activity(int(event.object_id))
        activity = normalize_strava_activity(activity_obj)
        StravaImportLog.objects.create(
            event_id=event.pk,
            alumno=alumno,
            actividad=None,
            strava_activity_id=activity["id"],
            attempt=attempt_no,
            status=StravaImportLog.Status.FETCHED,
            reason="ok",
            details={"type": activity.get("type")},
        )
    except Exception as exc:
        fetch_error = exc
        classification = _classify_transient_strava_error(exc) or "fetch_error"

        # Caso especial: 401 -> forzar refresh y reintentar UNA VEZ en el mismo intento
        if classification == "unauthorized":
            try:
                refreshed = obtener_cliente_strava_para_alumno(alumno, force_refresh=True)
                if refreshed:
                    activity_obj = refreshed.get_activity(int(event.object_id))
                    activity = normalize_strava_activity(activity_obj)
                    StravaImportLog.objects.create(
                        event_id=event.pk,
                        alumno=alumno,
                        actividad=None,
                        strava_activity_id=activity["id"],
                        attempt=attempt_no,
                        status=StravaImportLog.Status.FETCHED,
                        reason="ok_after_forced_refresh",
                        details={"type": activity.get("type")},
                    )
                    fetch_error = None
                else:
                    fetch_error = exc
            except Exception as exc2:
                fetch_error = exc2

        if activity is None:
            StravaImportLog.objects.create(
                event_id=event.pk,
                alumno=alumno,
                actividad=None,
                strava_activity_id=event.object_id,
                attempt=attempt_no,
                status=StravaImportLog.Status.FAILED,
                reason=classification,
                details={"error": str(fetch_error or exc)},
            )

            # Retry (backoff exponencial + jitter via Celery autoretry)
            if classification in {"rate_limit", "timeout", "server_error", "network"}:
                retries = int(getattr(self.request, "retries", 0))
                if retries >= int(getattr(self, "max_retries", 0)):
                    StravaWebhookEvent.objects.filter(pk=event.pk).update(
                        status=StravaWebhookEvent.Status.FAILED,
                        last_error=f"max_retries_exceeded:{classification}: {fetch_error or exc}",
                        processed_at=timezone.now(),
                    )
                    StravaActivitySyncState.objects.filter(
                        provider=event.provider, strava_activity_id=int(event.object_id)
                    ).update(
                        status=StravaActivitySyncState.Status.FAILED,
                        last_error=f"max_retries_exceeded:{classification}: {fetch_error or exc}",
                        locked_at=None,
                        locked_by_event_uid="",
                        last_attempt_at=timezone.now(),
                    )
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    _log_strava_ingest(
                        msg="strava.process_event.failed",
                        event_uid=event_uid,
                        correlation_id=correlation_id,
                        athlete_id=int(event.owner_id),
                        activity_id=int(event.object_id),
                        status="failed",
                        reason="max_retries_exceeded",
                        attempt=attempt_no,
                        duration_ms=duration_ms,
                        metric_failed=1,
                    )
                    return "FAILED: max_retries_exceeded"

                StravaWebhookEvent.objects.filter(pk=event.pk).update(
                    status=StravaWebhookEvent.Status.QUEUED,
                    last_error=f"{classification}: {fetch_error or exc}",
                )
                # Mantener el lock RUNNING para evitar otros pipelines mientras reintenta.
                StravaActivitySyncState.objects.filter(
                    provider=event.provider, strava_activity_id=int(event.object_id)
                ).update(
                    status=StravaActivitySyncState.Status.RUNNING,
                    locked_at=timezone.now(),
                    locked_by_event_uid=event_uid,
                    last_error=f"{classification}: {fetch_error or exc}",
                    last_attempt_at=timezone.now(),
                )
                raise StravaTransientError(f"{classification}: {fetch_error or exc}")

            StravaWebhookEvent.objects.filter(pk=event.pk).update(
                status=StravaWebhookEvent.Status.FAILED,
                last_error=str(fetch_error or exc),
                processed_at=timezone.now(),
            )
            StravaActivitySyncState.objects.filter(
                provider=event.provider, strava_activity_id=int(event.object_id)
            ).update(
                status=StravaActivitySyncState.Status.FAILED,
                last_error=str(fetch_error or exc),
                locked_at=None,
                locked_by_event_uid="",
                last_attempt_at=timezone.now(),
            )
            return f"FAIL: {fetch_error or exc}"

    # Reglas estrictas de aceptación
    invalid_reason = ""
    if not supported_strava_activity_type(activity.get("type")):
        invalid_reason = "unsupported_type"
    elif not activity.get("start_date_local"):
        invalid_reason = "missing_start_date"
    elif (activity.get("elapsed_time_s") or 0) <= 0 or (activity.get("moving_time_s") or 0) <= 0:
        invalid_reason = "invalid_duration"
    elif (activity.get("distance_m") or 0) <= 0:
        invalid_reason = "invalid_distance"
    elif activity.get("athlete_id") and int(activity["athlete_id"]) != int(event.owner_id):
        invalid_reason = "athlete_mismatch"

    # Upsert Actividad (dedupe) - identidad canónica: (source, source_object_id)
    mapped = map_strava_activity_to_actividad(activity)
    source = mapped.pop("source")
    source_object_id = mapped.pop("source_object_id")
    payload_sanitized = bool(activity.get("raw_sanitized"))

    defaults = {
        **mapped,
        "validity": Actividad.Validity.DISCARDED if invalid_reason else Actividad.Validity.VALID,
        "invalid_reason": invalid_reason or "",
    }

    actividad_obj, created = upsert_actividad(
        alumno=alumno,
        usuario=alumno.entrenador,
        source=source,
        source_object_id=source_object_id,
        defaults=defaults,
    )

    _log_strava_activity_upserted(
        alumno_id=alumno.id,
        source=source,
        source_object_id=source_object_id,
        upsert_created=bool(created),
        payload_sanitized=bool(payload_sanitized),
    )

    if invalid_reason:
        StravaImportLog.objects.create(
            event_id=event.pk,
            alumno=alumno,
            actividad=actividad_obj,
            strava_activity_id=activity["id"],
            attempt=attempt_no,
            status=StravaImportLog.Status.DISCARDED,
            reason=invalid_reason,
            details={"type": activity.get("type")},
        )
        StravaWebhookEvent.objects.filter(pk=event.pk).update(status=StravaWebhookEvent.Status.IGNORED, last_error="")
        StravaActivitySyncState.objects.filter(provider=event.provider, strava_activity_id=int(event.object_id)).update(
            status=StravaActivitySyncState.Status.DISCARDED,
            discard_reason=invalid_reason,
            last_error="",
            locked_at=None,
            locked_by_event_uid="",
            last_attempt_at=timezone.now(),
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        _log_strava_ingest(
            msg="strava.process_event.discarded",
            event_uid=event_uid,
            correlation_id=correlation_id,
            athlete_id=int(event.owner_id),
            activity_id=int(activity["id"]),
            status="discarded",
            reason=invalid_reason,
            attempt=attempt_no,
            duration_ms=duration_ms,
            metric_ignored=1,
        )
        return f"DISCARDED: {invalid_reason}"

    # Upsert Entrenamiento (plan match / unplanned)
    fecha = activity["start_date_local"].date()
    with transaction.atomic():
        entreno = Entrenamiento.objects.select_for_update().filter(strava_id=str(activity["id"])).first()
        accion = "UPDATED"
        if not entreno:
            entreno = Entrenamiento.objects.select_for_update().filter(
                alumno=alumno, fecha_asignada=fecha, completado=False
            ).first()
            if entreno:
                accion = "MATCHED"
        if not entreno:
            entreno = Entrenamiento(alumno=alumno, fecha_asignada=fecha, titulo=activity.get("name") or "Strava")
            accion = "CREATED_UNPLANNED"

        entreno.strava_id = str(activity["id"])
        entreno.completado = True
        entreno.tipo_actividad = _map_strava_type_to_core(activity.get("type"))
        entreno.distancia_real_km = round(float(activity.get("distance_m") or 0.0) / 1000.0, 2)
        entreno.tiempo_real_min = int(round(float(activity.get("moving_time_s") or 0) / 60.0))
        entreno.desnivel_real_m = int(round(float(activity.get("elevation_m") or 0.0)))
        if accion.startswith("CREATED") or entreno.titulo == "Entrenamiento":
            entreno.titulo = activity.get("name") or entreno.titulo
        entreno.save()

    StravaImportLog.objects.create(
        event_id=event.pk,
        alumno=alumno,
        actividad=actividad_obj,
        strava_activity_id=activity["id"],
        attempt=attempt_no,
        status=StravaImportLog.Status.SAVED,
        reason=accion,
        details={"entrenamiento_id": entreno.id},
    )

    # Plan vs Actual + Alertas (recalculable ante updates)
    try:
        from analytics.models import SessionComparison
        from analytics.plan_vs_actual import PlannedVsActualComparator
        from analytics.alerts import run_alert_triggers_for_comparison

        comparator = PlannedVsActualComparator()
        planned_session = None if accion == "CREATED_UNPLANNED" else entreno
        result = comparator.compare(planned_session, actividad_obj)

        comparison, _ = SessionComparison.objects.update_or_create(
            activity=actividad_obj,
            defaults={
                "entrenador_id": alumno.entrenador_id,
                "equipo_id": alumno.equipo_id,
                "alumno_id": alumno.id,
                "fecha": fecha,
                "planned_session": planned_session,
                "metrics_json": result.metrics,
                "compliance_score": int(result.compliance_score),
                "classification": result.classification,
                "explanation": result.explanation,
                "next_action": result.next_action,
            },
        )
        run_alert_triggers_for_comparison(comparison)
    except Exception as exc:
        # No bloquea la ingesta principal: queda en logs/import state.
        logger.exception(
            "strava.plan_vs_actual.error",
            extra={"event_uid": event_uid, "event_id": event_id, "error": str(exc)},
        )

    StravaWebhookEvent.objects.filter(pk=event.pk).update(status=StravaWebhookEvent.Status.PROCESSED, processed_at=timezone.now())
    StravaActivitySyncState.objects.filter(provider=event.provider, strava_activity_id=int(activity["id"])).update(
        status=StravaActivitySyncState.Status.SUCCEEDED,
        discard_reason="",
        last_error="",
        locked_at=None,
        locked_by_event_uid="",
        last_attempt_at=timezone.now(),
    )

    duration_ms = int((time.monotonic() - t0) * 1000)
    _log_strava_ingest(
        msg="strava.process_event.done",
        event_uid=event_uid,
        correlation_id=correlation_id,
        athlete_id=int(event.owner_id),
        activity_id=int(activity["id"]),
        status="succeeded",
        reason=accion,
        attempt=attempt_no,
        duration_ms=duration_ms,
        metric_processed=1,
    )
    return f"OK: {accion}"


@shared_task(bind=True)
def procesar_actividad_strava(self, object_id, owner_id):
    """
    Wrapper legacy (compat): crea un StravaWebhookEvent sintético y delega al pipeline robusto.
    """
    synthetic_uid = f"legacy:{owner_id}:{object_id}:create"
    event, created = StravaWebhookEvent.objects.get_or_create(
        event_uid=synthetic_uid,
        defaults={
            "object_type": "activity",
            "object_id": int(object_id),
            "aspect_type": "create",
            "owner_id": int(owner_id),
            "payload_raw": {"legacy": True, "object_id": object_id, "owner_id": owner_id},
            "status": StravaWebhookEvent.Status.QUEUED,
        },
    )
    if created:
        process_strava_event.delay(event.pk)
    return f"ENQUEUED: {event.pk}"