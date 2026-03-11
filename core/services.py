from dataclasses import dataclass
import datetime
import json
import time
from typing import Iterable, Optional

import logging

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from allauth.socialaccount.models import SocialToken, SocialApp  # noqa: legacy — guarded by DISABLE_LEGACY_STRAVA_SYNC; scheduled for removal in P1
from stravalib.client import Client  # noqa: legacy — guarded by DISABLE_LEGACY_STRAVA_SYNC; scheduled for removal in P1

from analytics.injury_risk import compute_injury_risk
from analytics.models import PMCHistory
from analytics.plan_vs_actual import PlannedVsActualComparator
from .models import (
    Alumno,
    Entrenamiento,
    BloqueEntrenamiento,
    PasoEntrenamiento,
    Actividad,
    PlantillaEntrenamientoVersion,
)
from .schema_v1 import compute_metrics_v1
from .utils.logging import safe_extra

# PR15 — Outbound delivery imports
from core.providers import SUPPORTED_PROVIDERS
from core.provider_capabilities import provider_supports, CAP_OUTBOUND_WORKOUTS
from integrations.outbound.workout_delivery import queue_workout_delivery

logger = logging.getLogger(__name__)

# ==============================================================================
#  1. CLONADOR UNIVERSAL (EL NÚCLEO DE LA AUTOMATIZACIÓN)
# ==============================================================================

def copiar_estructura_plantilla(entrenamiento, plantilla):
    """
    Toma un entrenamiento (existente o recién creado) y le inyecta 
    una COPIA PROFUNDA (Deep Copy) de la estructura JSON de la plantilla.
    Calcula métricas planificadas usando el servicio V1.
    NO toca modelos legacy (BloqueEntrenamiento/PasoEntrenamiento).
    """
    logger.info(
        "plantillas.copiar_estructura",
        extra=safe_extra({"entrenamiento_id": entrenamiento.id, "plantilla_id": plantilla.id}),
    )
    
    try:
        # 1. Copia de Estructura JSON (Deep Copy implícito al asignar dict)
        estructura_copy = dict(plantilla.estructura) if plantilla.estructura else {}
        entrenamiento.estructura = estructura_copy
        entrenamiento.estructura_schema_version = "1.0"

        # 2. Cálculo de métricas V1
        metrics = compute_metrics_v1(estructura_copy)
        entrenamiento.distancia_planificada_km = metrics.get("distance_km")
        entrenamiento.tiempo_planificado_min = metrics.get("duration_min")
        # tss_estimate could be used later

        # 3. Datos de cabecera
        if not entrenamiento.titulo or entrenamiento.titulo.strip() == "":
            entrenamiento.titulo = plantilla.titulo
        
        entrenamiento.tipo_actividad = plantilla.deporte
        entrenamiento.descripcion_detallada = plantilla.descripcion_global

        # 4. GUARDADO FINAL
        entrenamiento.save()
        
    except Exception:
        logger.exception(
            "plantillas.copiar_estructura_failed",
            extra=safe_extra({"entrenamiento_id": entrenamiento.id, "plantilla_id": plantilla.id}),
        )
        raise

# ==============================================================================
#  2. ASIGNACIÓN MASIVA (USA EL CLONADOR ACTUALIZADO)
# ==============================================================================

def asignar_plantilla_a_alumno(plantilla, alumno, fecha):
    """
    Crea o actualiza (idempotente) un entrenamiento planificado para un alumno.
    Usa la estructura JSON vigente de la plantilla y versionado.
    """
    logger.info(
        "plantillas.asignar_inicio",
        extra=safe_extra({"plantilla_id": plantilla.id, "alumno_id": alumno.id, "fecha": str(fecha)}),
    )

    try:
        plantilla_version = plantilla.versiones.order_by("-version").first()
        if not plantilla_version:
            plantilla_version = PlantillaEntrenamientoVersion.objects.create(
                plantilla=plantilla,
                version=1,
                estructura=plantilla.estructura,
                descripcion=plantilla.descripcion_global,
            )
        estructura_snapshot = dict(plantilla_version.estructura) if plantilla_version.estructura else {}
        
        # Calcular métricas V1
        metrics = compute_metrics_v1(estructura_snapshot)
        dist_km = metrics.get("distance_km")
        dur_min = metrics.get("duration_min")

        with transaction.atomic():
            entrenamiento, created = Entrenamiento.objects.select_for_update().get_or_create(
                alumno=alumno,
                plantilla_origen=plantilla,
                fecha_asignada=fecha,
                defaults={
                    "plantilla_version": plantilla_version,
                    "titulo": plantilla.titulo,
                    "tipo_actividad": plantilla.deporte,
                    "descripcion_detallada": plantilla.descripcion_global,
                    "estructura": estructura_snapshot,
                    "estructura_schema_version": "1.0",
                    "distancia_planificada_km": dist_km,
                    "tiempo_planificado_min": dur_min,
                    "completado": False,
                },
            )

            if not created and not entrenamiento.completado:
                entrenamiento.plantilla_version = plantilla_version
                entrenamiento.titulo = plantilla.titulo
                entrenamiento.tipo_actividad = plantilla.deporte
                entrenamiento.descripcion_detallada = plantilla.descripcion_global
                entrenamiento.estructura = estructura_snapshot
                entrenamiento.estructura_schema_version = "1.0"
                entrenamiento.distancia_planificada_km = dist_km
                entrenamiento.tiempo_planificado_min = dur_min
                entrenamiento.save(
                    update_fields=[
                        "plantilla_version",
                        "titulo",
                        "tipo_actividad",
                        "descripcion_detallada",
                        "estructura",
                        "estructura_schema_version",
                        "distancia_planificada_km",
                        "tiempo_planificado_min",
                    ]
                )

            return entrenamiento, created

    except Exception:
        logger.exception(
            "plantillas.asignar_failed",
            extra=safe_extra({"plantilla_id": plantilla.id, "alumno_id": alumno.id, "fecha": str(fecha)}),
        )
        raise

# ==============================================================================
#  3. EL JUEZ: LÓGICA DE CRUCE V2 (INTACTA)
# ==============================================================================

def ejecutar_cruce_inteligente(actividad):
    """
    Algoritmo 'El Juez' V2:
    1. Busca si la actividad YA estaba vinculada (Update).
    2. Si no, busca un plan PENDIENTE (Match).
    3. Califica cumplimiento (%).

    # noqa: legacy — writes real fields onto Entrenamiento (Law 3 violation).
    # Guarded at runtime by DISABLE_LEGACY_STRAVA_SYNC (default=True).
    # Scheduled for removal in P1 once reconciliation migrates fully to
    # services_reconciliation.py / WorkoutReconciliation model.
    """
    _ensure_legacy_strava_sync_allowed("ejecutar_cruce_inteligente")
    logger.info(
        "cruce_inteligente.evaluar",
        extra=safe_extra({"actividad_id": actividad.id, "strava_id": actividad.strava_id}),
    )

    email_usuario = actividad.usuario.email
    # Scope by usuario FK (deterministic, avoids cross-tenant email collision).
    alumno = Alumno.objects.filter(usuario=actividad.usuario).first()
    if alumno is None:
        # Fallback for legacy records where usuario FK is absent: match by email.
        alumno = Alumno.objects.filter(email=email_usuario).first()

    if not alumno:
        return False

    # --- BÚSQUEDA DUAL ---
    # 1. ¿Re-procesar existente? (Prioridad a lo ya vinculado)
    entrenamiento_objetivo = Entrenamiento.objects.filter(strava_id=str(actividad.strava_id)).first()

    if entrenamiento_objetivo:
        logger.info(
            "cruce_inteligente.reprocesar",
            extra=safe_extra({"entrenamiento_id": entrenamiento_objetivo.id}),
        )
    else:
        # 2. ¿Nuevo Match? (Buscar por fecha y estado pendiente)
        fecha_actividad = actividad.fecha_inicio.date()
        entrenamiento_objetivo = Entrenamiento.objects.filter(
            alumno=alumno,
            fecha_asignada=fecha_actividad,
            completado=False 
        ).first()

    if not entrenamiento_objetivo:
        return False

    # --- FUSIÓN ---
    try:
        with transaction.atomic():
            if not entrenamiento_objetivo.strava_id:
                logger.info(
                    "cruce_inteligente.match_vinculado",
                    extra=safe_extra({"entrenamiento_id": entrenamiento_objetivo.id}),
                )
            
            # 1. Datos Reales (Normalizados)
            dist_real_km = round(actividad.distancia / 1000, 2)
            tiempo_real_min = int(actividad.tiempo_movimiento / 60)
            
            entrenamiento_objetivo.distancia_real_km = dist_real_km
            entrenamiento_objetivo.tiempo_real_min = tiempo_real_min
            entrenamiento_objetivo.desnivel_real_m = int(actividad.desnivel_positivo)
            entrenamiento_objetivo.strava_id = str(actividad.strava_id)
            # Guardamos fecha real por si difiere de la asignada
            # (No tenemos campo fecha_ejecucion en el modelo actual, usamos la asignada o creamos uno si quieres)
            
            # 2. SCORE DE CUMPLIMIENTO
            cumplimiento = 0
            
            # Prioridad A: Comparar por Distancia
            if entrenamiento_objetivo.distancia_planificada_km and entrenamiento_objetivo.distancia_planificada_km > 0:
                cumplimiento = (dist_real_km / entrenamiento_objetivo.distancia_planificada_km) * 100
            
            # Prioridad B: Comparar por Tiempo
            elif entrenamiento_objetivo.tiempo_planificado_min and entrenamiento_objetivo.tiempo_planificado_min > 0:
                cumplimiento = (tiempo_real_min / entrenamiento_objetivo.tiempo_planificado_min) * 100
            
            # Prioridad C: Entrenamiento libre
            else:
                cumplimiento = 100 
            
            # Límite lógico visual (max 120%)
            if cumplimiento > 120: cumplimiento = 120
            entrenamiento_objetivo.porcentaje_cumplimiento = int(cumplimiento)

            # 3. Sensores (Si existen en el JSON)
            raw = actividad.datos_brutos
            if 'average_watts' in raw:
                entrenamiento_objetivo.potencia_promedio = int(raw['average_watts'])
            if 'average_heartrate' in raw:
                entrenamiento_objetivo.frecuencia_cardiaca_promedio = int(raw['average_heartrate'])

            # 4. Guardar y Calcular Métricas Fisiológicas
            entrenamiento_objetivo.completado = True
            entrenamiento_objetivo.save()

            # Llamada asíncrona (simulada aquí) a la calculadora de TSS/TRIMP
            from .tasks import procesar_metricas_entrenamiento
            procesar_metricas_entrenamiento(entrenamiento_objetivo.id)
            
            logger.info(
                "cruce_inteligente.fusion_ok",
                extra=safe_extra(
                    {
                        "entrenamiento_id": entrenamiento_objetivo.id,
                        "score": entrenamiento_objetivo.porcentaje_cumplimiento,
                    }
                ),
            )
            return True

    except Exception:
        logger.exception(
            "cruce_inteligente.fusion_failed",
            extra=safe_extra({"actividad_id": actividad.id, "strava_id": actividad.strava_id}),
        )
        return False

# ==============================================================================
#  3.1. RECONCILIACIÓN AUTOMÁTICA (PLANIFICADO vs REAL)
# ==============================================================================


@dataclass(frozen=True)
class ReconciliationOutcome:
    matched: bool
    entrenamiento_id: Optional[int]
    confidence: float
    compliance_score: int
    classification: str
    injury_risk_level: Optional[str]
    injury_risk_score: Optional[int]
    injury_risk_reasons: list[str]
    load_adjustment_suggestion: str


def _normalize_activity_type(value: Optional[str]) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"RUN", "VIRTUALRUN", "VIRTUAL_RUN"}:
        return "RUN"
    if raw in {"TRAIL", "TRAILRUN", "TRAIL_RUN", "TRAILRUNNING"}:
        return "TRAIL"
    if raw in {"RIDE", "CYCLING", "BIKE", "ROADBIKERIDE", "GRAVELRIDE"}:
        return "CYCLING"
    if raw in {"MTB", "MOUNTAINBIKERIDE"}:
        return "MTB"
    if raw in {"VIRTUALRIDE", "INDOORBIKERIDE", "INDOOR_BIKE"}:
        return "INDOOR_BIKE"
    if raw in {"SWIM", "SWIMMING", "POOLSWIM"}:
        return "SWIMMING"
    if raw in {"STRENGTH", "GYM", "WEIGHTTRAINING"}:
        return "STRENGTH"
    if raw in {"CARDIO"}:
        return "CARDIO"
    return "OTHER"


def _plan_types_for_activity(normalized: str) -> set[str]:
    if normalized in {"RUN", "TRAIL"}:
        return {"RUN", "TRAIL"}
    if normalized in {"CYCLING", "MTB", "INDOOR_BIKE"}:
        return {"CYCLING", "MTB", "INDOOR_BIKE"}
    if normalized == "SWIMMING":
        return {"SWIMMING"}
    if normalized == "STRENGTH":
        return {"STRENGTH"}
    if normalized == "CARDIO":
        return {"CARDIO"}
    return {"OTHER"}


def _primary_plan_type(normalized: str) -> str:
    if normalized in {"RUN", "TRAIL"}:
        return normalized
    if normalized in {"CYCLING", "MTB", "INDOOR_BIKE"}:
        return "CYCLING" if normalized == "CYCLING" else normalized
    return normalized


def _load_pmc_inputs(
    *,
    alumno_id: int,
    reference_date: datetime.date,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], Iterable[float]]:
    latest = (
        PMCHistory.objects.filter(alumno_id=alumno_id, sport="ALL", fecha__lte=reference_date)
        .order_by("-fecha")
        .values("ctl", "atl", "tsb")
        .first()
    )
    atl_7d_ago = (
        PMCHistory.objects.filter(alumno_id=alumno_id, sport="ALL", fecha=reference_date - datetime.timedelta(days=7))
        .values_list("atl", flat=True)
        .first()
    )
    last_3_days = (
        PMCHistory.objects.filter(alumno_id=alumno_id, sport="ALL", fecha__lte=reference_date)
        .order_by("-fecha")
        .values_list("tss_diario", flat=True)[:3]
    )
    if not latest:
        return None, None, None, None, list(last_3_days)
    return (
        float(latest["ctl"]),
        float(latest["atl"]),
        float(latest["tsb"]),
        float(atl_7d_ago) if atl_7d_ago is not None else None,
        list(last_3_days),
    )


def reconcile_activity_with_plan(
    *,
    activity: Actividad,
    allow_date_shift_days: int = 1,
) -> ReconciliationOutcome:
    """
    Vincula automáticamente una Actividad real con un Entrenamiento planificado.

    Criterios:
    - mismo alumno
    - fecha cercana (± allow_date_shift_days)
    - deporte compatible (RUN/TRAIL, CYCLING/MTB/INDOOR_BIKE, etc.)
    - entrenamiento pendiente y sin actividad ya vinculada
    """
    if activity.entrenamiento_id:
        return ReconciliationOutcome(
            matched=True,
            entrenamiento_id=activity.entrenamiento_id,
            confidence=float(activity.reconciliation_score or 0),
            compliance_score=0,
            classification="on_track",
            injury_risk_level=None,
            injury_risk_score=None,
            injury_risk_reasons=[],
            load_adjustment_suggestion="",
        )
    alumno = activity.alumno
    if not alumno:
        return ReconciliationOutcome(
            matched=False,
            entrenamiento_id=None,
            confidence=0.0,
            compliance_score=0,
            classification="anomaly",
            injury_risk_level=None,
            injury_risk_score=None,
            injury_risk_reasons=[],
            load_adjustment_suggestion="",
        )

    activity_date = timezone.localtime(activity.fecha_inicio).date()
    normalized = _normalize_activity_type(activity.tipo_deporte or activity.strava_sport_type)
    plan_types = _plan_types_for_activity(normalized)
    primary_type = _primary_plan_type(normalized)

    window_start = activity_date - datetime.timedelta(days=allow_date_shift_days)
    window_end = activity_date + datetime.timedelta(days=allow_date_shift_days)

    candidates = (
        Entrenamiento.objects.filter(
            alumno=alumno,
            fecha_asignada__range=(window_start, window_end),
            completado=False,
            tipo_actividad__in=plan_types,
        )
        .filter(actividades_reconciliadas__isnull=True)
        .order_by("fecha_asignada")
    )

    best_match = None
    best_score = -1.0
    for candidate in candidates:
        day_diff = abs((candidate.fecha_asignada - activity_date).days)
        score = 100.0 - (day_diff * 15.0)
        if candidate.tipo_actividad == primary_type:
            score += 5.0
        if score > best_score:
            best_score = score
            best_match = candidate

    if not best_match:
        return ReconciliationOutcome(
            matched=False,
            entrenamiento_id=None,
            confidence=0.0,
            compliance_score=0,
            classification="anomaly",
            injury_risk_level=None,
            injury_risk_score=None,
            injury_risk_reasons=[],
            load_adjustment_suggestion="",
        )

    dist_real_km = round(float(activity.distancia or 0.0) / 1000.0, 2)
    tiempo_real_min = int(float(activity.tiempo_movimiento or 0.0) / 60.0)
    elev_gain_m = activity.elev_gain_m if activity.elev_gain_m is not None else activity.desnivel_positivo
    desnivel_real_m = int(float(elev_gain_m or 0.0))

    comparator = PlannedVsActualComparator()
    comparison = comparator.compare(best_match, activity)

    with transaction.atomic():
        best_match.distancia_real_km = dist_real_km
        best_match.tiempo_real_min = tiempo_real_min
        best_match.desnivel_real_m = desnivel_real_m
        best_match.strava_id = str(activity.strava_id) if activity.strava_id else best_match.strava_id
        best_match.completado = True
        best_match.save()

        activity.entrenamiento = best_match
        activity.reconciled_at = timezone.now()
        activity.reconciliation_score = max(0.0, min(100.0, best_score))
        activity.reconciliation_method = "auto_date_sport"
        activity.save(
            update_fields=[
                "entrenamiento",
                "reconciled_at",
                "reconciliation_score",
                "reconciliation_method",
            ]
        )

    ctl, atl, tsb, atl_7d_ago, last_3_days = _load_pmc_inputs(
        alumno_id=alumno.id,
        reference_date=activity_date,
    )
    if ctl is None or atl is None or tsb is None:
        injury_risk_level = None
        injury_risk_score = None
        injury_risk_reasons: list[str] = []
        load_adjustment_suggestion = ""
    else:
        risk = compute_injury_risk(
            ctl=ctl,
            atl=atl,
            tsb=tsb,
            atl_7d_ago=atl_7d_ago,
            last_3_days_tss=last_3_days,
        )
        injury_risk_level = risk.risk_level
        injury_risk_score = risk.risk_score
        injury_risk_reasons = risk.risk_reasons
        if risk.risk_level == "HIGH":
            load_adjustment_suggestion = (
                "Reducir carga planificada 20–40% en los próximos 7 días, "
                "añadir 1–2 días de recuperación activa y evitar intensidad alta."
            )
        elif risk.risk_level == "MEDIUM":
            load_adjustment_suggestion = (
                "Reducir intensidad 10–20% o sustituir una sesión clave por trabajo aeróbico suave."
            )
        else:
            load_adjustment_suggestion = "Carga dentro de rango. Mantener progresión actual."

    return ReconciliationOutcome(
        matched=True,
        entrenamiento_id=best_match.id,
        confidence=max(0.0, min(100.0, best_score)),
        compliance_score=comparison.compliance_score,
        classification=comparison.classification,
        injury_risk_level=injury_risk_level,
        injury_risk_score=injury_risk_score,
        injury_risk_reasons=injury_risk_reasons,
        load_adjustment_suggestion=load_adjustment_suggestion,
    )

# ==============================================================================
#  4. SYNC STRAVA (INTACTO)
# ==============================================================================

def force_refresh_strava_token(user):
    """
    Fuerza refresh del token de Strava aunque `expires_at` no haya vencido.

    Útil para casos 401 (token revocado/desincronizado) detectados en webhooks.
    Devuelve True si refrescó, False si no pudo.
    """
    try:
        social_token = SocialToken.objects.filter(account__user=user, account__provider="strava").first()
        if not social_token:
            return False

        app_config = social_token.app or SocialApp.objects.filter(provider="strava").first()
        if not app_config:
            return False

        client = Client()
        refresh_response = client.refresh_access_token(
            client_id=app_config.client_id,
            client_secret=app_config.secret,
            refresh_token=social_token.token_secret,
        )
        social_token.token = refresh_response["access_token"]
        social_token.token_secret = refresh_response["refresh_token"]
        social_token.expires_at = timezone.make_aware(
            datetime.datetime.fromtimestamp(refresh_response["expires_at"])
        )
        social_token.app = app_config
        social_token.save()
        return True
    except Exception:
        return False


def obtener_cliente_strava(user, force_refresh: bool = False):
    try:
        social_token = SocialToken.objects.filter(account__user=user, account__provider='strava').first()
        if not social_token: return None

        client = Client()
        client.access_token = social_token.token
        client.refresh_token = social_token.token_secret
        
        token_expira_en = social_token.expires_at
        if force_refresh:
            # Refresh forzado (p.ej. tras 401)
            if not force_refresh_strava_token(user):
                return None
            # Re-leer token actualizado
            social_token = SocialToken.objects.filter(account__user=user, account__provider="strava").first()
            if not social_token:
                return None
            client.access_token = social_token.token
            client.refresh_token = social_token.token_secret
            return client

        if token_expira_en and timezone.now() > token_expira_en:
            app_config = social_token.app
            if not app_config:
                app_config = SocialApp.objects.filter(provider='strava').first()
                if app_config:
                    social_token.app = app_config
                    social_token.save()
            if not app_config: return None

            try:
                refresh_response = client.refresh_access_token(
                    client_id=app_config.client_id,
                    client_secret=app_config.secret,
                    refresh_token=social_token.token_secret
                )
                social_token.token = refresh_response['access_token']
                social_token.token_secret = refresh_response['refresh_token']
                social_token.expires_at = timezone.make_aware(datetime.datetime.fromtimestamp(refresh_response['expires_at']))
                social_token.save()

                client.access_token = social_token.token
                client.refresh_token = social_token.token_secret
            except Exception as exc:
                logger.warning(
                    "strava.token.refresh_failed",
                    extra=safe_extra({
                        "event_name": "strava.token.refresh_failed",
                        "provider": "strava",
                        "outcome": "fail",
                        "reason_code": "TOKEN_REFRESH_ERROR",
                        "exc_type": type(exc).__name__,
                    }),
                )
                return None
        return client
    except Exception as exc:
        logger.warning(
            "strava.token.lookup_failed",
            extra=safe_extra({
                "event_name": "strava.token.lookup_failed",
                "provider": "strava",
                "outcome": "fail",
                "reason_code": "TOKEN_LOOKUP_ERROR",
                "exc_type": type(exc).__name__,
            }),
        )
        return None


def obtener_cliente_strava_para_alumno(alumno: Alumno, *, force_refresh: bool = False):
    """
    Resuelve el token Strava correcto para importar actividades de un Alumno.

    Preferencias (primary + compat + SaaS):
    1. OAuthCredential PRIMARY: si existe OAuthCredential(provider=strava, alumno=...) lo usamos.
    2. SocialToken LEGACY: si OAuthCredential ausente, fallback a SocialToken vía allauth.
    3. Fallback coach: compat con setups legacy donde el entrenador conectó Strava.

    Logs reason_code para auditoría en producción:
      CRED_PRIMARY_OAUTHCREDENTIAL  → token desde OAuthCredential
      CRED_FALLBACK_ALLAUTH         → token desde SocialToken (allauth)
      CRED_NOT_FOUND                → sin credenciales disponibles
    """
    # --- PRIMARY: OAuthCredential (canonical store) ---
    from core.models import OAuthCredential as _OAuthCred

    _alumno_id = getattr(alumno, "pk", None)

    cred = (
        _OAuthCred.objects
        .filter(alumno=alumno, provider="strava")
        .first()
    )

    if cred is not None:
        # Build client from OAuthCredential
        client = Client()
        access = cred.access_token
        refresh = cred.refresh_token

        # Refresh if expired or forced
        now = timezone.now()
        if force_refresh or (cred.expires_at is not None and now >= cred.expires_at):
            try:
                app_config = SocialApp.objects.filter(provider="strava").first()
                if not app_config:
                    logger.warning(
                        "strava.auth.lookup",
                        extra=safe_extra({
                            "event_name": "strava.auth.lookup",
                            "alumno_id": _alumno_id,
                            "provider": "strava",
                            "reason_code": "CRED_PRIMARY_OAUTHCREDENTIAL",
                            "outcome": "fail",
                            "detail": "no_socialapp_for_refresh",
                        }),
                    )
                    # Fall through to legacy path
                    cred = None
                else:
                    temp_client = Client()
                    refresh_response = temp_client.refresh_access_token(
                        client_id=app_config.client_id,
                        client_secret=app_config.secret,
                        refresh_token=refresh,
                    )
                    access = refresh_response["access_token"]
                    refresh = refresh_response.get("refresh_token", refresh)
                    expires_at = timezone.make_aware(
                        datetime.datetime.fromtimestamp(refresh_response["expires_at"])
                    )
                    # Persist refreshed tokens back to OAuthCredential
                    _OAuthCred.objects.filter(pk=cred.pk).update(
                        access_token=access,
                        refresh_token=refresh,
                        expires_at=expires_at,
                    )
                    client.access_token = access
                    client.refresh_token = refresh
                    logger.info(
                        "strava.auth.lookup",
                        extra=safe_extra({
                            "event_name": "strava.auth.lookup",
                            "alumno_id": _alumno_id,
                            "provider": "strava",
                            "reason_code": "CRED_PRIMARY_OAUTHCREDENTIAL",
                            "outcome": "ok",
                            "refreshed": True,
                        }),
                    )
                    return client
            except Exception:
                logger.exception(
                    "strava.auth.lookup",
                    extra=safe_extra({
                        "event_name": "strava.auth.lookup",
                        "alumno_id": _alumno_id,
                        "provider": "strava",
                        "reason_code": "CRED_PRIMARY_OAUTHCREDENTIAL",
                        "outcome": "fail",
                        "detail": "refresh_exception",
                    }),
                )
                cred = None  # Fall through to legacy

        if cred is not None:
            client.access_token = access
            client.refresh_token = refresh
            logger.info(
                "strava.auth.lookup",
                extra=safe_extra({
                    "event_name": "strava.auth.lookup",
                    "alumno_id": _alumno_id,
                    "provider": "strava",
                    "reason_code": "CRED_PRIMARY_OAUTHCREDENTIAL",
                    "outcome": "ok",
                    "refreshed": False,
                }),
            )
            return client

    # --- LEGACY: SocialToken (allauth) — backward compat ---
    def _try_social_token_for_user(user):
        if not user:
            return None
        result = obtener_cliente_strava(user, force_refresh=force_refresh)
        if result:
            logger.info(
                "strava.auth.lookup",
                extra=safe_extra({
                    "event_name": "strava.auth.lookup",
                    "alumno_id": _alumno_id,
                    "provider": "strava",
                    "reason_code": "CRED_FALLBACK_ALLAUTH",
                    "outcome": "ok",
                }),
            )
        return result

    # Preferir token del atleta (modelo recomendado)
    if getattr(alumno, "usuario_id", None):
        athlete_client = _try_social_token_for_user(alumno.usuario)
        if athlete_client:
            return athlete_client

    # Fallback legacy: token del coach
    if getattr(alumno, "entrenador_id", None):
        coach_client = _try_social_token_for_user(alumno.entrenador)
        if coach_client:
            return coach_client

    logger.warning(
        "strava.auth.lookup",
        extra=safe_extra({
            "event_name": "strava.auth.lookup",
            "alumno_id": _alumno_id,
            "provider": "strava",
            "reason_code": "CRED_NOT_FOUND",
            "outcome": "fail",
        }),
    )
    return None


class LegacyStravaSyncDisabled(RuntimeError):
    """LEGACY PIPELINE — DO NOT USE IN PROD. Kept only for admin/dev compatibility."""


def _ensure_legacy_strava_sync_allowed(origin: str) -> None:
    if getattr(settings, "DISABLE_LEGACY_STRAVA_SYNC", True):
        logger.warning(
            "Legacy Strava sync blocked (%s). Set DISABLE_LEGACY_STRAVA_SYNC=False to allow.",
            origin,
        )
        raise LegacyStravaSyncDisabled(
            "LEGACY PIPELINE — DO NOT USE IN PROD. "
            "Legacy Strava sync is disabled via DISABLE_LEGACY_STRAVA_SYNC."
        )


def sincronizar_actividades_strava(user, dias_historial=None):
    # LEGACY PIPELINE — DO NOT USE IN PROD. Kept only for admin/dev compatibility.
    _ensure_legacy_strava_sync_allowed("sincronizar_actividades_strava")
    client = obtener_cliente_strava(user)
    if not client: return 0, 0, "Token inválido."

    nuevas = 0
    actualizadas = 0

    try:
        logger.info("strava.legacy_sync_start", extra=safe_extra({"user_id": user.id}))
        
        if dias_historial:
            start_time = timezone.now() - datetime.timedelta(days=dias_historial)
            logger.info(
                "strava.legacy_sync_history_window",
                extra=safe_extra({"user_id": user.id, "start_date": str(start_time.date())}),
            )
            activities = client.get_activities(after=start_time)
        else:
            activities = client.get_activities(limit=10)

        for activity in activities:
            tiempo_s = 0
            raw_time = activity.moving_time
            if raw_time:
                try: 
                    if hasattr(raw_time, 'total_seconds'): tiempo_s = int(raw_time.total_seconds())
                    elif hasattr(raw_time, 'seconds'): tiempo_s = int(raw_time.seconds)
                    else: tiempo_s = int(raw_time)
                except: tiempo_s = 0
            
            distancia_m = 0.0
            if activity.distance:
                try:
                    if hasattr(activity.distance, 'magnitude'): distancia_m = float(activity.distance.magnitude)
                    else: distancia_m = float(activity.distance)
                except: pass

            elevacion_m = 0.0
            if activity.total_elevation_gain:
                try:
                    if hasattr(activity.total_elevation_gain, 'magnitude'): elevacion_m = float(activity.total_elevation_gain.magnitude)
                    else: elevacion_m = float(activity.total_elevation_gain)
                except: pass
            
            mapa_str = activity.map.summary_polyline if activity.map else None

            datos_backup = {}
            try:
                if hasattr(activity, 'to_dict'): raw_data = activity.to_dict()
                elif hasattr(activity, 'model_dump'): raw_data = activity.model_dump()
                else: raw_data = {"info": str(activity)}
                datos_backup = json.loads(json.dumps(raw_data, cls=DjangoJSONEncoder))
            except: datos_backup = {}

            obj, created = Actividad.objects.update_or_create(
                strava_id=activity.id, 
                defaults={
                    'usuario': user,
                    'nombre': activity.name,
                    'distancia': distancia_m,
                    'tiempo_movimiento': tiempo_s,
                    'fecha_inicio': activity.start_date_local,
                    'tipo_deporte': activity.type,
                    'desnivel_positivo': elevacion_m,
                    'elev_gain_m': float(elevacion_m or 0.0),
                    'elev_loss_m': 0.0,
                    'elev_total_m': float(elevacion_m or 0.0),
                    'mapa_polilinea': mapa_str,
                    'datos_brutos': datos_backup
                }
            )
            
            ejecutar_cruce_inteligente(obj)

            if created: nuevas += 1
            else: actualizadas += 1
        
        if dias_historial:
             from analytics.utils import recalcular_historial_completo
             alumno = Alumno.objects.filter(email=user.email).first()
             if alumno:
                 recalcular_historial_completo(alumno)

        logger.info(
            "strava.legacy_sync_ok",
            extra=safe_extra({"user_id": user.id, "nuevas": nuevas, "actualizadas": actualizadas}),
        )
        return nuevas, actualizadas, "OK"

    except Exception:
        logger.exception(
            "strava.legacy_sync_failed",
            extra=safe_extra({"user_id": user.id}),
        )
        return nuevas, actualizadas, "Error técnico"


# ==============================================================================
#  PR15: OUTBOUND DELIVERY TRIGGER
# ==============================================================================

def trigger_workout_delivery_if_applicable(entrenamiento, *, actor_user=None) -> None:
    """
    PR15 — Trigger outbound delivery for a PlannedWorkout.

    Enqueues queue_workout_delivery ONLY for providers that:
      1. Appear in SUPPORTED_PROVIDERS (PR12 registry)
      2. Declare CAP_OUTBOUND_WORKOUTS (PR13) — Strava does NOT
      3. Have a live OAuthCredential with status="connected" (PR11)

    Fail-closed contract:
      - Missing alumno / entrenador → log warning + return (never raise).
      - Any unexpected exception is caught and logged; never propagates to HTTP layer.

    Multi-tenant:
      organization_id = alumno.entrenador_id  (coach user pk = tenant key in MTP).

    This function is fire-and-forget: callers do not inspect the return value.
    """
    try:
        alumno = getattr(entrenamiento, "alumno", None)
        if alumno is None:
            logger.warning(
                "workout_delivery_trigger.missing_alumno",
                extra=safe_extra({"entrenamiento_id": getattr(entrenamiento, "id", None)}),
            )
            return

        organization_id = getattr(alumno, "entrenador_id", None)
        if not organization_id:
            logger.warning(
                "workout_delivery_trigger.missing_organization",
                extra=safe_extra({
                    "entrenamiento_id": getattr(entrenamiento, "id", None),
                    "alumno_id": alumno.pk,
                }),
            )
            return

        athlete_id = alumno.pk
        planned_workout_id = entrenamiento.pk

        # Lazy import to avoid circular dependency at import-time
        from core.oauth_credentials import compute_connection_status

        eligible_providers = []

        for provider in SUPPORTED_PROVIDERS:
            # Gate 1: capability check (no DB hit)
            if not provider_supports(provider, CAP_OUTBOUND_WORKOUTS):
                continue

            # Gate 2: connection status (reads OAuthCredential)
            cs = compute_connection_status(alumno=alumno, provider=provider)
            if cs.status != "connected":
                continue

            # Provider is eligible — enqueue delivery
            queue_workout_delivery(
                organization_id=organization_id,
                athlete_id=athlete_id,
                provider=provider,
                planned_workout_id=planned_workout_id,
                payload={},
            )
            eligible_providers.append(provider)

        logger.info(
            "workout_delivery_trigger.completed",
            extra=safe_extra({
                "event_name": "workout_delivery_trigger.completed",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "planned_workout_id": planned_workout_id,
                "eligible_providers": eligible_providers,
                "actor_user_id": getattr(actor_user, "id", None),
            }),
        )

    except Exception:  # noqa: BLE001 — fire-and-forget, must never break HTTP flow
        logger.exception(
            "workout_delivery_trigger.unexpected_error",
            extra=safe_extra({
                "entrenamiento_id": getattr(entrenamiento, "id", None),
                "actor_user_id": getattr(actor_user, "id", None),
            }),
        )
