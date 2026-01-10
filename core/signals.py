import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Alumno
from django.db import transaction
from django.utils import timezone

from allauth.socialaccount.signals import social_account_added, social_account_updated

from .models import ExternalIdentity
from .tasks import drain_strava_events_for_athlete
from .metrics import (
    generar_pronosticos_alumno, 
    calcular_vam_desde_tests, 
    calcular_ritmos_series # <--- IMPORTACIÓN CLAVE
)

logger = logging.getLogger(__name__)
def _has_field(obj, name: str) -> bool:
    # Evita crashes si el modelo no tiene ciertos campos (compat/migraciones desalineadas)
    return hasattr(obj, name)

def _safe_set(obj, name: str, value):
    if _has_field(obj, name):
        setattr(obj, name, value)

@receiver(post_save, sender=Alumno)
def actualizar_pronosticos_alumno(sender, instance, created, **kwargs):
    """
    Cerebro Automático del Alumno (Versión 4.5):
    1. Auto-estima VAM desde tests de campo.
    2. Auto-estima VO2max.
    3. Genera Pronósticos de Carrera (Calle y Trail).
    4. Genera Ritmos de Entrenamiento (Series 100m-2000m).
    """
    # Evitamos recursión infinita
    if hasattr(instance, '_skip_signal'): return

    # --- FASE 1: AUTO-ESTIMACIÓN DE VAM ---
    vam_operativa = instance.vam_actual
    
    # Si la VAM es 0 o nula, intentamos calcularla científicamente desde los tests
    if not vam_operativa or vam_operativa == 0:
        vam_calculada = calcular_vam_desde_tests(
            cooper_km=getattr(instance, "test_cooper_distancia", 0) or 0,
            tiempo_1k=getattr(instance, "test_1k_tiempo", 0) or 0,
            tiempo_5k=getattr(instance, "test_5k_tiempo", 0) or 0,
        )
        if vam_calculada > 0:
            logger.info(
                "alumno.vam_calculada",
                extra={"alumno_id": instance.id, "vam": round(vam_calculada, 2)},
            )
            vam_operativa = vam_calculada
            instance.vam_actual = vam_calculada 

    # --- FASE 2: AUTO-ESTIMACIÓN DE VO2 MAX ---
    # Si tenemos VAM pero no VO2max, usamos la fórmula de Léger & Mercier
    if vam_operativa > 0 and (not instance.vo2_max or instance.vo2_max == 0):
        instance.vo2_max = round(vam_operativa * 3.5, 1)

    # --- FASE 3: PREDICCIONES Y RITMOS (OUTPUTS) ---
    if vam_operativa > 0:
        logger.info(
            "alumno.pronosticos_generados",
            extra={"alumno_id": instance.id, "vam": round(vam_operativa, 2)},
        )
        
        # A. Pronósticos de Carrera (9 valores)
        (p10, p21, p42, 
         pt21, pt42, pt60, pt80, pt100, pt160) = generar_pronosticos_alumno(vam_operativa)
        
        # Asignar Calle
        _safe_set(instance, "prediccion_10k", p10)
        _safe_set(instance, "prediccion_21k", p21)
        _safe_set(instance, "prediccion_42k", p42)
        
        # Asignar Trail
        _safe_set(instance, "prediccion_trail_21k", pt21)
        _safe_set(instance, "prediccion_trail_42k", pt42)
        _safe_set(instance, "prediccion_trail_60k", pt60)
        _safe_set(instance, "prediccion_trail_80k", pt80)
        _safe_set(instance, "prediccion_trail_100k", pt100)
        _safe_set(instance, "prediccion_trail_160k", pt160)

        # B. Ritmos de Series (NUEVO)
        series = calcular_ritmos_series(vam_operativa)
        if series:
            _safe_set(instance, "ritmo_serie_100m", series.get('100m', '-'))
            _safe_set(instance, "ritmo_serie_200m", series.get('200m', '-'))
            _safe_set(instance, "ritmo_serie_250m", series.get('250m', '-'))
            _safe_set(instance, "ritmo_serie_400m", series.get('400m', '-'))
            _safe_set(instance, "ritmo_serie_500m", series.get('500m', '-'))
            _safe_set(instance, "ritmo_serie_800m", series.get('800m', '-'))
            _safe_set(instance, "ritmo_serie_1000m", series.get('1000m', '-'))
            _safe_set(instance, "ritmo_serie_1200m", series.get('1200m', '-'))
            _safe_set(instance, "ritmo_serie_1600m", series.get('1600m', '-'))
            _safe_set(instance, "ritmo_serie_2000m", series.get('2000m', '-'))
        
        # Marcamos para saltar esta señal en el próximo guardado interno
        instance._skip_signal = True 
        instance.save()
        
    else:
        # Limpieza si se borran los datos (Reset)
        if getattr(instance, "prediccion_10k", ""):
             _safe_set(instance, "prediccion_10k", "")
             _safe_set(instance, "prediccion_21k", "")
             _safe_set(instance, "prediccion_42k", "")
             _safe_set(instance, "prediccion_trail_21k", "")
             _safe_set(instance, "prediccion_trail_42k", "")
             _safe_set(instance, "prediccion_trail_60k", "")
             _safe_set(instance, "prediccion_trail_80k", "")
             _safe_set(instance, "prediccion_trail_100k", "")
             _safe_set(instance, "prediccion_trail_160k", "")
             
             # Limpiar series también
             _safe_set(instance, "ritmo_serie_100m", "")
             _safe_set(instance, "ritmo_serie_200m", "")
             _safe_set(instance, "ritmo_serie_400m", "")
             _safe_set(instance, "ritmo_serie_1000m", "")
             # ... (el resto se limpiará al guardar vacío)
             
             instance._skip_signal = True
             instance.save()


@receiver(post_save, sender=Alumno)
def ensure_external_identity_link(sender, instance: Alumno, created: bool, **kwargs):
    """
    Linking canónico (admin/manual):
    Si un `Alumno` tiene `strava_athlete_id`, garantizamos que exista `ExternalIdentity(strava, athlete_id)`
    y que quede linkeada a este Alumno. Si el link se creó/actualizó, drenamos eventos pendientes.

    Importante: es idempotente y no re-encola en cada save (solo si hubo cambio real de link).
    """
    if hasattr(instance, "_skip_signal"):
        return

    # `Alumno.strava_athlete_id` puede ser int/str/None (p.ej. admin/manual o imports).
    # Normalizamos defensivamente para evitar `.strip()` sobre ints y castear a `int` una sola vez.
    athlete_id_raw = instance.strava_athlete_id
    if athlete_id_raw is None:
        return

    athlete_id_str = ""
    athlete_id_int = None
    if isinstance(athlete_id_raw, int):
        athlete_id_int = athlete_id_raw
        athlete_id_str = str(athlete_id_int)
    elif isinstance(athlete_id_raw, str):
        athlete_id_str = athlete_id_raw.strip()
        if not athlete_id_str:
            return
        try:
            athlete_id_int = int(athlete_id_str)
        except (TypeError, ValueError):
            return
    else:
        # Tipo inesperado: fail-safe, no bloquear el save().
        return

    # En este punto siempre tenemos un int válido para usar en Celery y una forma canónica stringificada.
    external_user_id = str(athlete_id_int)

    def _on_commit_drain():
        try:
            drain_strava_events_for_athlete.delay(provider="strava", owner_id=athlete_id_int)
        except Exception:
            # Nunca bloquear saves por encolado.
            pass

    # Crear o vincular identidad canónica.
    try:
        identity, created_identity = ExternalIdentity.objects.get_or_create(
            provider=ExternalIdentity.Provider.STRAVA,
            external_user_id=external_user_id,
            defaults={
                "alumno": instance,
                "status": ExternalIdentity.Status.LINKED,
                "linked_at": timezone.now(),
            },
        )
        # Si ya existía pero estaba unlinked o linkeada a otro alumno, corregimos.
        if (not created_identity) and identity.alumno_id != instance.id:
            ExternalIdentity.objects.filter(pk=identity.pk).update(
                alumno=instance,
                status=ExternalIdentity.Status.LINKED,
                linked_at=timezone.now(),
            )
            transaction.on_commit(_on_commit_drain)
        elif created_identity:
            transaction.on_commit(_on_commit_drain)
        else:
            # Ya estaba linkeado a este alumno: no drenar (idempotencia).
            pass
    except Exception:
        # No romper el guardado del alumno por un problema auxiliar.
        return


def _extract_strava_athlete_id_from_sociallogin(sociallogin) -> str:
    """
    allauth/Strava: el `uid` suele ser el athlete_id.
    Fallback: intentar leer del extra_data si existe.
    """
    try:
        uid = getattr(getattr(sociallogin, "account", None), "uid", None)
        if uid:
            return str(uid).strip()
    except Exception:
        pass

    try:
        extra = getattr(getattr(sociallogin, "account", None), "extra_data", None) or {}
        athlete = extra.get("athlete") or {}
        if isinstance(athlete, dict) and athlete.get("id"):
            return str(athlete["id"]).strip()
    except Exception:
        pass
    return ""


@receiver(social_account_added)
@receiver(social_account_updated)
def link_strava_on_oauth(sender, request, sociallogin, **kwargs):
    """
    Linking por OAuth:
    Cuando el usuario conecta Strava, linkeamos su `Alumno` (si existe) a la identidad externa
    y drenamos eventos pendientes.
    """
    try:
        account = getattr(sociallogin, "account", None)
        if not account or getattr(account, "provider", None) != "strava":
            return
        user = getattr(sociallogin, "user", None)
        if not user:
            return

        athlete_id = _extract_strava_athlete_id_from_sociallogin(sociallogin)
        if not athlete_id:
            return

        alumno = Alumno.objects.filter(usuario=user).first()
        if not alumno:
            # Usuario sin perfil Alumno todavía: el webhook igual queda en LINK_REQUIRED.
            return

        # 1) Backfill compat: setear strava_athlete_id si faltaba (admin-friendly).
        if not (alumno.strava_athlete_id or "").strip():
            alumno._skip_signal = True  # evita que se dispare el cerebro de pronósticos en este save
            alumno.strava_athlete_id = str(int(athlete_id))
            alumno.save(update_fields=["strava_athlete_id"])

        # 2) Link canónico + drain (idempotente).
        identity, created_identity = ExternalIdentity.objects.get_or_create(
            provider=ExternalIdentity.Provider.STRAVA,
            external_user_id=str(int(athlete_id)),
            defaults={
                "alumno": alumno,
                "status": ExternalIdentity.Status.LINKED,
                "linked_at": timezone.now(),
                "profile": getattr(account, "extra_data", None) or {},
            },
        )
        if (not created_identity) and identity.alumno_id != alumno.id:
            ExternalIdentity.objects.filter(pk=identity.pk).update(
                alumno=alumno,
                status=ExternalIdentity.Status.LINKED,
                linked_at=timezone.now(),
                profile=getattr(account, "extra_data", None) or {},
            )

        transaction.on_commit(lambda: drain_strava_events_for_athlete.delay(provider="strava", owner_id=int(athlete_id)))
    except Exception:
        return
