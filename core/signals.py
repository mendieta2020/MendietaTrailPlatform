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
    Extract unique Strava athlete ID from sociallogin.
    Priority order: extra_data.athlete.id, extra_data.athlete_id, account.uid (if digits).
    """
    try:
        account = getattr(sociallogin, "account", None)
        if not account:
            return ""
        
        extra = getattr(account, "extra_data", None) or {}
        
        # Priority 1: athlete.id (nested dict)
        athlete = extra.get("athlete") or {}
        if isinstance(athlete, dict) and athlete.get("id"):
            return str(athlete["id"]).strip()
        
        # Priority 2: athlete_id (flat field)
        if extra.get("athlete_id"):
            return str(extra["athlete_id"]).strip()
        
        # Priority 3: account.uid if it's digits (fallback for some providers)
        uid = getattr(account, "uid", None)
        if uid and str(uid).isdigit():
            return str(uid).strip()
    except Exception:
        pass
    return ""


@receiver(social_account_added)
@receiver(social_account_updated)
def link_strava_on_oauth(sender, request, sociallogin, **kwargs):
    """
    Hardened OAuth linking (P0):
    - Validates access_token and athlete.id exist
    - Upserts ExternalIdentity deterministically
    - Upserts OAuthIntegrationStatus with connected/failed state
    - Triggers drain_strava_events_for_athlete on success
    
    Fail-closed: if validation fails, marks as failed in OAuthIntegrationStatus.
    """
    try:
        account = getattr(sociallogin, "account", None)
        if not account or getattr(account, "provider", None) != "strava":
            return
        
        user = getattr(sociallogin, "user", None)
        if not user:
            return
        
        # Get Alumno profile
        alumno = Alumno.objects.filter(usuario=user).first()
        if not alumno:
            # User without Alumno profile: cannot link yet
            logger.warning(
                "oauth.link.no_alumno_profile",
                extra={"user_id": user.id, "provider": "strava"},
            )
            return
        
        # Extract and validate OAuth data
        extra_data = getattr(account, "extra_data", None) or {}
        
        # Validation 1: access_token must exist
        access_token = extra_data.get("access_token")
        if not access_token:
            logger.error(
                "oauth.link.missing_access_token",
                extra={"user_id": user.id, "alumno_id": alumno.id, "provider": "strava"},
            )
            from .integration_models import OAuthIntegrationStatus
            OAuthIntegrationStatus.objects.update_or_create(
                alumno=alumno,
                provider="strava",
                defaults={
                    "connected": False,
                    "error_reason": "missing_access_token",
                    "error_message": "OAuth token exchange completed but access_token missing from response",
                    "last_error_at": timezone.now(),
                },
            )
            return
        
        # Validation 2: athlete.id must exist
        athlete_id = _extract_strava_athlete_id_from_sociallogin(sociallogin)
        if not athlete_id:
            logger.error(
                "oauth.link.missing_athlete_id",
                extra={"user_id": user.id, "alumno_id": alumno.id, "provider": "strava"},
            )
            from .integration_models import OAuthIntegrationStatus
            OAuthIntegrationStatus.objects.update_or_create(
                alumno=alumno,
                provider="strava",
                defaults={
                    "connected": False,
                    "error_reason": "missing_athlete_id",
                    "error_message": "OAuth token response missing athlete.id field",
                    "last_error_at": timezone.now(),
                },
            )
            return
        
        # SUCCESS PATH: Both validations passed
        
        # Extract token metadata for storage
        refresh_token = extra_data.get("refresh_token", "")
        expires_at_timestamp = extra_data.get("expires_at")
        expires_at = None
        if expires_at_timestamp:
            try:
                from datetime import datetime as dt, timezone as dt_timezone
                expires_at = dt.fromtimestamp(int(expires_at_timestamp), tz=dt_timezone.utc)
            except (ValueError, TypeError):
                expires_at = None
        
        # 1) Backfill compat: set strava_athlete_id on Alumno if missing (admin-friendly)
        if not (alumno.strava_athlete_id or "").strip():
            alumno._skip_signal = True  # Avoid triggering forecast recalc signal
            alumno.strava_athlete_id = str(int(athlete_id))
            alumno.save(update_fields=["strava_athlete_id"])
        
        # 2) Upsert canonical ExternalIdentity (deterministic linking)
        identity, created_identity = ExternalIdentity.objects.update_or_create(
            provider=ExternalIdentity.Provider.STRAVA,
            external_user_id=str(int(athlete_id)),
            defaults={
                "alumno": alumno,
                "status": ExternalIdentity.Status.LINKED,
                "linked_at": timezone.now(),
                "profile": extra_data,
            },
        )
        
        # If identity existed but pointed to different alumno, update it
        if not created_identity and identity.alumno_id != alumno.id:
            ExternalIdentity.objects.filter(pk=identity.pk).update(
                alumno=alumno,
                status=ExternalIdentity.Status.LINKED,
                linked_at=timezone.now(),
                profile=extra_data,
            )
        
        # 3) Upsert OAuthIntegrationStatus (source of truth for connected state)
        from .integration_models import OAuthIntegrationStatus
        integration_status, status_created = OAuthIntegrationStatus.objects.update_or_create(
            alumno=alumno,
            provider="strava",
            defaults={
                "connected": True,
                "athlete_id": str(int(athlete_id)),
                "expires_at": expires_at,
                "error_reason": "",
                "error_message": "",
                "last_error_at": None,
            },
        )
        
        logger.info(
            "oauth.link.success",
            extra={
                "user_id": user.id,
                "alumno_id": alumno.id,
                "provider": "strava",
                "athlete_id": athlete_id,
                "identity_created": created_identity,
                "status_created": status_created,
            },
        )
        
        # 4) Trigger backfill/drain of pending webhook events (async, fail-safe)
        try:
            transaction.on_commit(
                lambda: drain_strava_events_for_athlete.delay(
                    provider="strava",
                    owner_id=int(athlete_id),
                )
            )
        except Exception as e:
            # Non-critical: draining can be done manually if this fails
            logger.warning(
                "oauth.link.drain_failed_to_queue",
                extra={"alumno_id": alumno.id, "athlete_id": athlete_id, "error": str(e)},
            )
    
    except Exception as e:
        # Unexpected exception during linking: mark as failed in OAuthIntegrationStatus
        logger.exception(
            "oauth.link.unexpected_exception",
            extra={"user_id": user.id if user else None},
        )
        try:
            if alumno:
                from .integration_models import OAuthIntegrationStatus
                OAuthIntegrationStatus.objects.update_or_create(
                    alumno=alumno,
                    provider="strava",
                    defaults={
                        "connected": False,
                        "error_reason": "exception_during_link",
                        "error_message": f"{e.__class__.__name__}: {str(e)[:200]}",
                        "last_error_at": timezone.now(),
                    },
                )
        except Exception:
            pass  # Best effort
