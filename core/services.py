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
from allauth.socialaccount.models import SocialToken, SocialApp
from stravalib.client import Client

from analytics.injury_risk import compute_injury_risk
from analytics.models import PMCHistory
from analytics.plan_vs_actual import PlannedVsActualComparator
from .models import Alumno, Entrenamiento, BloqueEntrenamiento, PasoEntrenamiento, Actividad
from .utils.logging import safe_extra

logger = logging.getLogger(__name__)

# ==============================================================================
#  1. CLONADOR UNIVERSAL (EL NÚCLEO DE LA AUTOMATIZACIÓN)
# ==============================================================================

def copiar_estructura_plantilla(entrenamiento, plantilla):
    """
    Toma un entrenamiento (existente o recién creado) y le inyecta 
    una COPIA PROFUNDA (Deep Copy) de los bloques y pasos de la plantilla.
    Adapta la estructura nueva de objetivos flexibles (RPE, Zona VAM, Manual).
    """
    logger.info(
        "plantillas.copiar_estructura",
        extra=safe_extra({"entrenamiento_id": entrenamiento.id, "plantilla_id": plantilla.id}),
    )
    
    try:
        # 1. Limpieza previa (Evita duplicados si se edita y cambia la plantilla)
        entrenamiento.bloques_reales.all().delete()
        
        # 2. Clonado de Bloques
        bloques_origen = plantilla.bloques.all().order_by('orden')
        
        for bloque_orig in bloques_origen:
            nuevo_bloque = BloqueEntrenamiento.objects.create(
                entrenamiento=entrenamiento,
                plantilla=None, # Desvinculado para edición libre
                orden=bloque_orig.orden,
                nombre_bloque=bloque_orig.nombre_bloque,
                repeticiones=bloque_orig.repeticiones
            )
            
            # 3. Clonado de Pasos (NUEVA ESTRUCTURA FLEXIBLE)
            pasos_origen = bloque_orig.pasos.all().order_by('orden')
            for paso_orig in pasos_origen:
                PasoEntrenamiento.objects.create(
                    bloque=nuevo_bloque,
                    orden=paso_orig.orden,
                    fase=paso_orig.fase,
                    
                    # Datos de Tiempo/Distancia
                    tipo_duracion=paso_orig.tipo_duracion,
                    valor_duracion=paso_orig.valor_duracion,
                    unidad_duracion=paso_orig.unidad_duracion,
                    
                    # --- NUEVA LÓGICA DE OBJETIVOS (CORRECCIÓN CRÍTICA) ---
                    tipo_objetivo=paso_orig.tipo_objetivo,
                    objetivo_rpe=paso_orig.objetivo_rpe,
                    objetivo_zona_vam=paso_orig.objetivo_zona_vam,
                    objetivo_manual=paso_orig.objetivo_manual,
                    
                    # Textos y Multimedia
                    titulo_paso=paso_orig.titulo_paso,
                    nota_paso=paso_orig.nota_paso,
                    archivo_adjunto=paso_orig.archivo_adjunto, # Copia la referencia
                    enlace_url=paso_orig.enlace_url
                )
                
        # 4. Auto-completar título si no tiene uno
        if not entrenamiento.titulo or entrenamiento.titulo.strip() == "":
            entrenamiento.titulo = plantilla.titulo

        # 5. GUARDADO FINAL (EL GATILLO)
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
    Crea la cáscara del entrenamiento y delega el copiado al Clonador Universal.
    Calcula ritmos personalizados al final.
    """
    logger.info(
        "plantillas.asignar_inicio",
        extra=safe_extra({"plantilla_id": plantilla.id, "alumno_id": alumno.id, "fecha": str(fecha)}),
    )
    
    try:
        with transaction.atomic():
            # A. Crear la cáscara vacía
            nuevo_entreno = Entrenamiento.objects.create(
                alumno=alumno,
                plantilla_origen=plantilla,
                fecha_asignada=fecha,
                titulo=plantilla.titulo,
                tipo_actividad=plantilla.deporte,
                descripcion_detallada=plantilla.descripcion_global, # Copiamos la descripción
                completado=False
            )
            
            # B. Inyectar contenido (Bloques/Pasos)
            copiar_estructura_plantilla(nuevo_entreno, plantilla)
            
            # C. Calcular Totales y Ritmos Personalizados (MAGIA DE VAM)
            nuevo_entreno.calcular_totales_desde_estructura()
            
            # Si el modelo tiene la función de ritmos personalizados, la ejecutamos
            if hasattr(nuevo_entreno, 'calcular_objetivos_personalizados'):
                nuevo_entreno.calcular_objetivos_personalizados()
                
            nuevo_entreno.save()
            
            return nuevo_entreno

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
    """
    _ensure_legacy_strava_sync_allowed("ejecutar_cruce_inteligente")
    logger.info(
        "cruce_inteligente.evaluar",
        extra=safe_extra({"actividad_id": actividad.id, "strava_id": actividad.strava_id}),
    )

    email_usuario = actividad.usuario.email
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
    desnivel_real_m = int(float(activity.desnivel_positivo or 0.0))

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
            except: return None
        return client
    except: return None


def obtener_cliente_strava_para_alumno(alumno: Alumno, *, force_refresh: bool = False):
    """
    Resuelve el token Strava correcto para importar actividades de un Alumno.

    Preferencias (compat + SaaS):
    - Si el alumno tiene `usuario` y ese usuario conectó Strava (SocialToken), usamos ese token.
    - Si no, fallback al token del entrenador (compat con setups legacy).
    """
    # Preferir token del atleta (modelo recomendado)
    if getattr(alumno, "usuario_id", None):
        athlete_client = obtener_cliente_strava(alumno.usuario, force_refresh=force_refresh)
        if athlete_client:
            return athlete_client
    # Fallback legacy: token del coach
    if getattr(alumno, "entrenador_id", None):
        return obtener_cliente_strava(alumno.entrenador, force_refresh=force_refresh)
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

    except Exception as e:
        error_msg = f"Error técnico: {str(e)}"
        logger.exception(
            "strava.legacy_sync_failed",
            extra=safe_extra({"user_id": user.id}),
        )
        return nuevas, actualizadas, error_msg
