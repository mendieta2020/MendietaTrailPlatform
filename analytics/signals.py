from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from datetime import timedelta
from core.models import Entrenamiento, Alumno
from .models import HistorialFitness, AlertaRendimiento
from core.tasks import generar_feedback_ia
from core.metrics import generar_pronosticos_alumno # Importamos la lógica Riegel

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

    # Usamos TSS real (Potencia/GAP) o estimado
    tss_nuevo = instance.tss if instance.tss else 0
    
    if tss_nuevo == 0: return # Sin carga no hay impacto fisiológico

    alumno = instance.alumno
    fecha_entreno = instance.fecha_asignada
    
    print(f"🧬 [ANALYTICS] Impacto fisiológico detectado: {alumno} | TSS {tss_nuevo} | {fecha_entreno}")

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
        total_tss_dia = sum(e.tss for e in entrenamientos_dia if e.tss)
        
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
        print(f"   📈 PMC Actualizado -> CTL: {historial_hoy.ctl:.1f} | TSB: {historial_hoy.tsb:.1f}")


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
    # Usamos Potencia Normalizada (NP) o Promedio
    watts_sesion = instance.normalized_power if instance.normalized_power else instance.potencia_promedio
    
    # Umbral de Alerta: Si sostuvo el 95% de su FTP por más de 20 min, probablemente su FTP subió.
    if watts_sesion and alumno.ftp > 0:
        if watts_sesion >= (alumno.ftp * 0.95) and instance.tiempo_real_min > 20:
            crear_alerta_si_no_existe(alumno, instance.fecha_asignada, 'FTP_UP', watts_sesion, alumno.ftp, instance.titulo)

    # --- B. DETECCIÓN DE FC MÁXIMA ---
    if instance.frecuencia_cardiaca_promedio and alumno.fcm > 0:
        # Si el promedio de la sesión fue > 98% del Max teórico, el Max está mal.
        if instance.frecuencia_cardiaca_promedio > (alumno.fcm * 0.98):
             crear_alerta_si_no_existe(alumno, instance.fecha_asignada, 'HR_MAX', instance.frecuencia_cardiaca_promedio, alumno.fcm, instance.titulo)

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
        print(f"🚀 [ALERTA] {tipo} detectado para {alumno.nombre}")

# ==============================================================================
#  3. GATILLO DE FEEDBACK IA (CELERY)
# ==============================================================================

@receiver(post_save, sender=Entrenamiento)
def disparar_analisis_ia(sender, instance, created, **kwargs):
    """
    Solicita análisis cualitativo a la IA solo si hay datos reales.
    Usa on_commit para asegurar que el worker reciba el dato guardado.
    """
    if instance.completado and not instance.feedback_ia:
        has_data = (instance.tiempo_real_min and instance.tiempo_real_min > 0) or \
                   (instance.distancia_real_km and instance.distancia_real_km > 0)

        if has_data:
            print(f"🧠 [SIGNAL] Solicitando análisis IA para {instance}")
            # transaction.on_commit asegura que Celery no lea la DB antes de que Django escriba
            transaction.on_commit(lambda: generar_feedback_ia.apply_async(args=[instance.id], countdown=2))