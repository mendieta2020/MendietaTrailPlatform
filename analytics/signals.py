import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from datetime import timedelta
from core.models import Entrenamiento, Alumno
from .models import HistorialFitness, AlertaRendimiento
from core.tasks import generar_feedback_ia
from core.metrics import generar_pronosticos_alumno # Importamos la lógica Riegel

logger = logging.getLogger(__name__)
# ==============================================================================
#  1. CÁLCULO DE FITNESS (PMC - MODELO BANISTER)
# ==============================================================================

@receiver(post_save, sender=Entrenamiento)
def actualizar_fitness_atleta(sender, instance, created, **kwargs):
    """
    Cada vez que se guarda un entrenamiento completado,
    recalculamos el PMC (CTL/ATL/TSB) del día.
    """
    if not instance.completado: return

    def _load_score(entreno: Entrenamiento) -> float:
        """
        Fuente de carga robusta (compatible con modelos legacy/nuevos).

        - Si existe `tss`, lo prioriza.
        - Si no, usa heurística MVP: minutos * (1 + rpe/10).
        """
        tss = getattr(entreno, "tss", None)
        if tss is not None:
            try:
                return float(tss or 0)
            except Exception:
                return 0.0
        dur = float(getattr(entreno, "tiempo_real_min", 0) or 0)
        rpe = float(getattr(entreno, "rpe", 0) or 0)
        intensity = 1.0 + (max(0.0, min(10.0, rpe)) / 10.0)
        return dur * intensity

    tss_nuevo = _load_score(instance)
    if tss_nuevo == 0:
        return  # sin carga no hay impacto fisiológico

    alumno = instance.alumno
    fecha_entreno = instance.fecha_asignada
    
    logger.info(
        "analytics.impacto_fisiologico",
        extra={"alumno_id": alumno.id, "tss": round(tss_nuevo, 2), "fecha": str(fecha_entreno)},
    )

    # Ejecutamos dentro de una transacción atómica para integridad
    with transaction.atomic():
        # 1. Obtener registro del día (o crear vacío)
        historial_hoy, _ = HistorialFitness.objects.get_or_create(
            alumno=alumno,
            fecha=fecha_entreno
        )

        # 2. Sumar TODA la carga del día (Doble turno)
        entrenamientos_dia = Entrenamiento.objects.filter(
            alumno=alumno, 
            fecha_asignada=fecha_entreno, 
            completado=True
        )
        total_tss_dia = sum(_load_score(e) for e in entrenamientos_dia)
        
        historial_hoy.tss_diario = total_tss_dia
        
        # 3. CÁLCULO RECURSIVO (Coggan)
        # CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday) * (1/42)
        # ATL_today = ATL_yesterday + (TSS_today - ATL_yesterday) * (1/7)
        
        fecha_ayer = fecha_entreno - timedelta(days=1)
        historial_ayer = HistorialFitness.objects.filter(alumno=alumno, fecha=fecha_ayer).first()
        
        ctl_ayer = historial_ayer.ctl if historial_ayer else 0
        atl_ayer = historial_ayer.atl if historial_ayer else 0

        historial_hoy.ctl = ctl_ayer + (total_tss_dia - ctl_ayer) / 42
        historial_hoy.atl = atl_ayer + (total_tss_dia - atl_ayer) / 7
        historial_hoy.tsb = historial_hoy.ctl - historial_hoy.atl 

        historial_hoy.save()
        logger.info(
            "analytics.pmc_actualizado",
            extra={
                "alumno_id": alumno.id,
                "fecha": str(fecha_entreno),
                "ctl": round(historial_hoy.ctl, 2),
                "tsb": round(historial_hoy.tsb, 2),
            },
        )


# ==============================================================================
#  2. DETECCIÓN DE UMBRALES Y PREDICCIONES (IA DE RENDIMIENTO)
# ==============================================================================

@receiver(post_save, sender=Entrenamiento)
def analizar_rendimiento_y_predicciones(sender, instance, created, **kwargs):
    """
    Analiza si el atleta rompió sus límites teóricos y recalibra las predicciones.
    """
    if not instance.completado: return
    alumno = instance.alumno
    
    # --- A. DETECCIÓN DE FTP/VAM (Mejora de Rendimiento) ---
    # Compat: estas columnas pueden no existir según migraciones/historia del repo.
    watts_np = getattr(instance, "normalized_power", None)
    watts_avg = getattr(instance, "potencia_promedio", None)
    watts_sesion = watts_np or watts_avg
    alumno_ftp = getattr(alumno, "ftp", 0) or 0

    # Umbral de Alerta: Si sostuvo el 95% de su FTP por más de 20 min, probablemente su FTP subió.
    if watts_sesion and alumno_ftp > 0:
        if watts_sesion >= (alumno_ftp * 0.95) and (instance.tiempo_real_min or 0) > 20:
            crear_alerta_si_no_existe(alumno, instance.fecha_asignada, 'FTP_UP', watts_sesion, alumno_ftp, instance.titulo)

    # --- B. DETECCIÓN DE FC MÁXIMA ---
    hr_avg = getattr(instance, "frecuencia_cardiaca_promedio", None)
    if hr_avg and getattr(alumno, "fcm", 0) > 0:
        # Si el promedio de la sesión fue > 98% del Max teórico, el Max está mal.
        if hr_avg > (alumno.fcm * 0.98):
             crear_alerta_si_no_existe(alumno, instance.fecha_asignada, 'HR_MAX', hr_avg, alumno.fcm, instance.titulo)

    # --- C. ACTUALIZACIÓN DE PRONÓSTICOS (RIEGEL) ---
    # Si detectamos una mejora significativa o si es una carrera, actualizamos el modelo predictivo
    if instance.tipo_actividad in ['RUN', 'TRAIL'] and instance.completado:
        # Aquí podríamos poner lógica compleja. Por ahora, forzamos actualización
        # si se modifica el Alumno directamente en otra señal.
        # (La actualización automática vía VAM ya está en core/signals.py asociada al modelo Alumno)
        pass

def crear_alerta_si_no_existe(alumno, fecha, tipo, valor_nuevo, valor_viejo, contexto):
    """Helper para no spamear alertas."""
    if not AlertaRendimiento.objects.filter(alumno=alumno, fecha=fecha, tipo=tipo).exists():
        msg = f"Detectado en '{contexto}'. Valor: {valor_nuevo} (Anterior: {valor_viejo})"
        AlertaRendimiento.objects.create(
            alumno=alumno, tipo=tipo, 
            valor_detectado=valor_nuevo, valor_anterior=valor_viejo, 
            mensaje=msg
        )
        logger.info(
            "analytics.alerta_creada",
            extra={"alumno_id": alumno.id, "tipo": tipo, "fecha": str(fecha)},
        )

# ==============================================================================
#  3. GATILLO DE FEEDBACK IA (CELERY)
# ==============================================================================

@receiver(post_save, sender=Entrenamiento)
def disparar_analisis_ia(sender, instance, created, **kwargs):
    """
    Solicita análisis cualitativo a la IA solo si hay datos reales.
    Usa on_commit para asegurar que el worker reciba el dato guardado.
    """
    # Si el modelo no tiene `feedback_ia` (migraciones modernas), no disparamos esta señal.
    if not hasattr(instance, "feedback_ia"):
        return

    if instance.completado and not getattr(instance, "feedback_ia", None):
        has_data = (instance.tiempo_real_min and instance.tiempo_real_min > 0) or \
                   (instance.distancia_real_km and instance.distancia_real_km > 0)

        if has_data:
            logger.info(
                "analytics.feedback_ia_solicitado",
                extra={"entrenamiento_id": instance.id, "alumno_id": instance.alumno_id},
            )
            # transaction.on_commit asegura que Celery no lea la DB antes de que Django escriba
            transaction.on_commit(lambda: generar_feedback_ia.apply_async(args=[instance.id], countdown=2))
