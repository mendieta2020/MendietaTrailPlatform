from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Alumno
from .metrics import (
    generar_pronosticos_alumno, 
    calcular_vam_desde_tests, 
    calcular_ritmos_series # <--- IMPORTACIÓN CLAVE
)

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
            cooper_km=instance.test_cooper_distancia,
            tiempo_1k=instance.test_1k_tiempo,
            tiempo_5k=instance.test_5k_tiempo
        )
        if vam_calculada > 0:
            print(f"🧪 [CIENCIA] VAM Calculada por Tests de Campo: {vam_calculada} km/h")
            vam_operativa = vam_calculada
            instance.vam_actual = vam_calculada 

    # --- FASE 2: AUTO-ESTIMACIÓN DE VO2 MAX ---
    # Si tenemos VAM pero no VO2max, usamos la fórmula de Léger & Mercier
    if vam_operativa > 0 and (not instance.vo2_max or instance.vo2_max == 0):
        instance.vo2_max = round(vam_operativa * 3.5, 1)

    # --- FASE 3: PREDICCIONES Y RITMOS (OUTPUTS) ---
    if vam_operativa > 0:
        print(f"🔮 [PREDICCIÓN] Generando datos para {instance.nombre} (VAM: {vam_operativa})...")
        
        # A. Pronósticos de Carrera (9 valores)
        (p10, p21, p42, 
         pt21, pt42, pt60, pt80, pt100, pt160) = generar_pronosticos_alumno(vam_operativa)
        
        # Asignar Calle
        instance.prediccion_10k = p10
        instance.prediccion_21k = p21
        instance.prediccion_42k = p42
        
        # Asignar Trail
        instance.prediccion_trail_21k = pt21
        instance.prediccion_trail_42k = pt42
        instance.prediccion_trail_60k = pt60
        instance.prediccion_trail_80k = pt80
        instance.prediccion_trail_100k = pt100
        instance.prediccion_trail_160k = pt160

        # B. Ritmos de Series (NUEVO)
        series = calcular_ritmos_series(vam_operativa)
        if series:
            instance.ritmo_serie_100m = series.get('100m', '-')
            instance.ritmo_serie_200m = series.get('200m', '-')
            instance.ritmo_serie_250m = series.get('250m', '-')
            instance.ritmo_serie_400m = series.get('400m', '-')
            instance.ritmo_serie_500m = series.get('500m', '-')
            instance.ritmo_serie_800m = series.get('800m', '-')
            instance.ritmo_serie_1000m = series.get('1000m', '-')
            instance.ritmo_serie_1200m = series.get('1200m', '-')
            instance.ritmo_serie_1600m = series.get('1600m', '-')
            instance.ritmo_serie_2000m = series.get('2000m', '-')
        
        # Marcamos para saltar esta señal en el próximo guardado interno
        instance._skip_signal = True 
        instance.save()
        
    else:
        # Limpieza si se borran los datos (Reset)
        if instance.prediccion_10k:
             instance.prediccion_10k = ""
             instance.prediccion_21k = ""
             instance.prediccion_42k = ""
             instance.prediccion_trail_21k = ""
             instance.prediccion_trail_42k = ""
             instance.prediccion_trail_60k = ""
             instance.prediccion_trail_80k = ""
             instance.prediccion_trail_100k = ""
             instance.prediccion_trail_160k = ""
             
             # Limpiar series también
             instance.ritmo_serie_100m = ""
             instance.ritmo_serie_200m = ""
             instance.ritmo_serie_400m = ""
             instance.ritmo_serie_1000m = ""
             # ... (el resto se limpiará al guardar vacío)
             
             instance._skip_signal = True
             instance.save()