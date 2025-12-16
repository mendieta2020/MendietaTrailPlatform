# backend/analytics/utils.py
from core.models import Entrenamiento
from analytics.models import HistorialFitness
from django.db import transaction

def recalcular_historial_completo(alumno):
    """
    Borra el historial de fitness y lo reconstruye desde el primer entrenamiento
    hasta hoy, día por día, para asegurar la integridad matemática (CTL/ATL).
    """
    print(f"🧮 [RECALCULO] Iniciando reconstrucción total para {alumno.nombre}...")
    
    # 1. Borrar historial corrupto/viejo
    HistorialFitness.objects.filter(alumno=alumno).delete()
    
    # 2. Obtener TODOS los entrenamientos con carga (TSS), ordenados por fecha
    entrenamientos = Entrenamiento.objects.filter(
        alumno=alumno, 
        completado=True,
        tss__gt=0 # Solo los que tienen carga
    ).order_by('fecha_asignada')
    
    if not entrenamientos.exists():
        print("⚠️ No hay entrenamientos con TSS para calcular.")
        return

    # 3. Inicializar variables de Banister (Empezamos de cero)
    ctl_ayer = 0
    atl_ayer = 0
    
    # Vamos a procesar fecha por fecha
    # Agrupamos por fecha porque puede haber doble turno
    from itertools import groupby
    
    # Convertimos a lista para iterar
    lista_entrenos = list(entrenamientos)
    
    # Agrupar por fecha
    for fecha, grupo in groupby(lista_entrenos, key=lambda x: x.fecha_asignada):
        
        # Sumar TSS del día
        tss_dia = sum(e.tss for e in grupo)
        
        # Fórmulas de Coggan
        # CTL Hoy = CTL Ayer + (TSS Día - CTL Ayer) / 42
        ctl_hoy = ctl_ayer + (tss_dia - ctl_ayer) / 42
        atl_hoy = atl_ayer + (tss_dia - atl_ayer) / 7
        tsb_hoy = ctl_hoy - atl_hoy
        
        # Guardar registro limpio
        HistorialFitness.objects.create(
            alumno=alumno,
            fecha=fecha,
            tss_diario=tss_dia,
            ctl=ctl_hoy,
            atl=atl_hoy,
            tsb=tsb_hoy
        )
        
        # Actualizar acumuladores para mañana
        ctl_ayer = ctl_hoy
        atl_ayer = atl_hoy
        
    print(f"✅ [RECALCULO] Historial reconstruido hasta {fecha}. CTL Final: {ctl_ayer:.1f}")