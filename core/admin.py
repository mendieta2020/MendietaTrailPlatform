from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Equipo, Alumno, Pago, 
    PlantillaEntrenamiento, Entrenamiento, 
    Carrera, InscripcionCarrera, Actividad,
    ExternalIdentity,
)

# ==============================================================================
#  CONFIGURACIÓN DEL PANEL DE ADMINISTRACIÓN (MODERNO)
# ==============================================================================

@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cantidad_alumnos_visual', 'color_visual', 'created_at')
    search_fields = ('nombre', 'descripcion')

    def cantidad_alumnos_visual(self, obj):
        count = obj.cantidad_alumnos
        return f"{count} Atletas"
    cantidad_alumnos_visual.short_description = "Miembros"

    def color_visual(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 50%; border: 1px solid #ccc;"></div>',
            obj.color_identificador
        )
    color_visual.short_description = "Color"


@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'equipo', 'estado_actual', 'strava_athlete_id', 'ultimo_pago_status')
    list_filter = ('estado_actual', 'equipo', 'categoria')
    search_fields = ('nombre', 'apellido', 'email', 'strava_athlete_id')
    
    # Organizamos los campos en secciones
    fieldsets = (
        ('Información Personal', {
            'fields': ('usuario', 'entrenador', 'equipo', 'nombre', 'apellido', 'email', 'telefono', 'ciudad', 'strava_athlete_id')
        }),
        ('Estado y Finanzas', {
            'fields': ('estado_actual', 'fecha_ultimo_pago', 'esta_lesionado', 'apto_medico_al_dia')
        }),
        ('Fisiología & Zonas', {
            'fields': ('vo2_max', 'vam_actual', 'fcm', 'fcreposo', 'zonas_fc', 'zonas_velocidad')
        }),
    )

    def ultimo_pago_status(self, obj):
        return obj.situacion_financiera if hasattr(obj, 'situacion_financiera') else "-"
    ultimo_pago_status.short_description = "Estado Pago"


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = ("provider", "external_user_id", "status", "alumno", "linked_at", "updated_at")
    list_filter = ("provider", "status")
    search_fields = ("external_user_id", "alumno__nombre", "alumno__apellido", "alumno__email")
    readonly_fields = ("created_at", "updated_at", "linked_at")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('fecha_pago', 'alumno', 'monto', 'metodo', 'es_valido_visual')
    list_filter = ('es_valido', 'metodo', 'fecha_pago')
    search_fields = ('alumno__nombre', 'alumno__apellido')
    actions = ['validar_pagos']

    def es_valido_visual(self, obj):
        return "✅ Validado" if obj.es_valido else "⏳ Pendiente"
    es_valido_visual.short_description = "Estado"

    @admin.action(description='✅ Validar pagos seleccionados')
    def validar_pagos(self, request, queryset):
        queryset.update(es_valido=True)
        # Disparamos la señal de actualización manualmente si es necesario
        for pago in queryset:
            pago.save() # Esto fuerza la actualización de la fecha en el alumno


@admin.register(PlantillaEntrenamiento)
class PlantillaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'deporte', 'etiqueta_dificultad', 'created_at')
    list_filter = ('deporte', 'etiqueta_dificultad')
    search_fields = ('titulo', 'descripcion_global')
    readonly_fields = ('created_at',)


@admin.register(Entrenamiento)
class EntrenamientoAdmin(admin.ModelAdmin):
    list_display = ('fecha_asignada', 'alumno', 'titulo', 'tipo_actividad', 'completado', 'cumplimiento_visual')
    list_filter = ('completado', 'tipo_actividad', 'fecha_asignada')
    search_fields = ('titulo', 'alumno__nombre', 'alumno__apellido')
    date_hierarchy = 'fecha_asignada'
    
    fieldsets = (
        ('Asignación', {
            'fields': ('alumno', 'plantilla_origen', 'titulo', 'fecha_asignada', 'tipo_actividad')
        }),
        ('Planificación (JSON)', {
            'fields': ('estructura', 'descripcion_detallada')
        }),
        ('Métricas Planificadas', {
            'fields': ('distancia_planificada_km', 'tiempo_planificado_min', 'desnivel_planificado_m', 'intensidad_planificada')
        }),
        ('Resultados Reales', {
            'fields': ('completado', 'distancia_real_km', 'tiempo_real_min', 'rpe', 'feedback_alumno', 'porcentaje_cumplimiento')
        }),
    )

    def cumplimiento_visual(self, obj):
        if not obj.completado: return "-"
        if obj.porcentaje_cumplimiento >= 90:
            color = "green"
        elif obj.porcentaje_cumplimiento >= 50:
            color = "orange"
        else:
            color = "red"
        return format_html('<b style="color:{}">{}%</b>', color, obj.porcentaje_cumplimiento)
    cumplimiento_visual.short_description = "% Cump."


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'fecha', 'distancia_km', 'desnivel_positivo_m')
    search_fields = ('nombre',)
    list_filter = ('fecha',)


@admin.register(InscripcionCarrera)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'carrera', 'estado')
    list_filter = ('estado',)
    search_fields = ('alumno__nombre', 'carrera__nombre')


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'usuario', 'tipo_deporte', 'fecha_inicio', 'distancia')
    list_filter = ('tipo_deporte', 'fecha_inicio')
    search_fields = ('nombre', 'strava_id')