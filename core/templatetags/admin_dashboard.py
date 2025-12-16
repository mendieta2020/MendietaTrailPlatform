from django import template
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from core.models import Alumno, Pago

register = template.Library()

@register.simple_tag
def obtener_metricas_negocio():
    """
    Calcula los KPIs (Key Performance Indicators) del negocio en tiempo real.
    """
    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)
    # Definimos morosos como aquellos que no pagan hace más de 35 días
    fecha_limite_pago = hoy - timedelta(days=35)

    # Consultas optimizadas
    total_alumnos = Alumno.objects.count()
    activos = Alumno.objects.filter(estado_actual='ACTIVO').count()
    lesionados = Alumno.objects.filter(esta_lesionado=True).count()
    
    # Morosos (Lógica de negocio)
    # Filtramos los que tienen fecha de pago vieja O los que nunca pagaron y se dieron de alta hace mucho
    morosos = Alumno.objects.filter(
        fecha_ultimo_pago__lt=fecha_limite_pago
    ).exclude(estado_actual='BAJA').count()

    # Finanzas del Mes
    ingresos = Pago.objects.filter(fecha_pago__gte=inicio_mes).aggregate(Sum('monto'))['monto__sum']
    if ingresos is None: ingresos = 0

    return {
        'total': total_alumnos,
        'activos': activos,
        'lesionados': lesionados,
        'morosos': morosos,
        'ingresos_mes': ingresos,
    }