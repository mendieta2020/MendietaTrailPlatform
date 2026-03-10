from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Equipo, Alumno, Pago,
    PlantillaEntrenamiento, Entrenamiento,
    Carrera, InscripcionCarrera, Actividad,
    ExternalIdentity, CompletedActivity,
    Organization, Team, Membership,
    Coach, Athlete, AthleteCoachAssignment,
    AthleteProfile, RaceEvent, AthleteGoal, WorkoutLibrary,
    PlannedWorkout, WorkoutBlock, WorkoutInterval,
    WorkoutAssignment,
    ActivityStream,
    WorkoutReconciliation,
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


@admin.register(CompletedActivity)
class CompletedActivityAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'organization', 'alumno', 'athlete', 'sport', 'provider', 'start_time', 'duration_s', 'distance_m')
    list_filter = ('provider', 'sport', 'start_time')
    search_fields = ('provider_activity_id', 'alumno__nombre', 'alumno__apellido')
    readonly_fields = ('created_at',)
    raw_id_fields = ('organization', 'alumno', 'athlete')


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active", "organization")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("joined_at",)


@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_active", "years_experience", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "coach", "team", "is_active", "created_at")
    list_filter = ("organization", "is_active", "team")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AthleteCoachAssignment)
class AthleteCoachAssignmentAdmin(admin.ModelAdmin):
    list_display = ("athlete", "coach", "organization", "role", "assigned_at", "ended_at")
    list_filter = ("role", "organization")
    search_fields = ("athlete__user__username", "coach__user__username")
    readonly_fields = ("assigned_at", "updated_at")


@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):
    list_display = ("athlete", "organization", "weight_kg", "ftp_watts", "vo2max", "is_injured", "updated_at")
    list_filter = ("organization", "is_injured", "dominant_discipline")
    search_fields = ("athlete__user__username",)
    readonly_fields = ("updated_at",)


@admin.register(RaceEvent)
class RaceEventAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "discipline", "event_date", "location", "country", "distance_km")
    list_filter = ("organization", "discipline", "event_date")
    search_fields = ("name", "location", "country")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AthleteGoal)
class AthleteGoalAdmin(admin.ModelAdmin):
    list_display = ("title", "athlete", "organization", "priority", "goal_type", "status", "target_date", "target_event")
    list_filter = ("organization", "priority", "status", "goal_type")
    search_fields = ("title", "athlete__user__username", "coach_notes")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WorkoutLibrary)
class WorkoutLibraryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_public", "created_by", "created_at")
    list_filter = ("organization", "is_public")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PlannedWorkout)
class PlannedWorkoutAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "library", "discipline", "session_type", "estimated_duration_seconds", "created_at")
    list_filter = ("organization", "discipline", "session_type")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("library",)


@admin.register(WorkoutBlock)
class WorkoutBlockAdmin(admin.ModelAdmin):
    list_display = ("planned_workout", "organization", "order_index", "block_type", "name", "created_at")
    list_filter = ("organization", "block_type")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("planned_workout",)


@admin.register(WorkoutInterval)
class WorkoutIntervalAdmin(admin.ModelAdmin):
    list_display = ("block", "organization", "order_index", "metric_type", "duration_seconds", "distance_meters", "created_at")
    list_filter = ("organization", "metric_type")
    search_fields = ("description", "target_label")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("block",)


@admin.register(WorkoutAssignment)
class WorkoutAssignmentAdmin(admin.ModelAdmin):
    list_display = ("athlete", "planned_workout", "organization", "scheduled_date", "day_order", "status", "assigned_by", "assigned_at")
    list_filter = ("organization", "status", "scheduled_date")
    search_fields = ("athlete__user__username", "athlete__user__email", "planned_workout__name", "coach_notes", "athlete_notes")
    readonly_fields = ("assigned_at", "updated_at", "effective_date")
    raw_id_fields = ("athlete", "planned_workout")


@admin.register(ActivityStream)
class ActivityStreamAdmin(admin.ModelAdmin):
    list_display = ("completed_activity", "stream_type", "provider", "created_at")
    list_filter = ("stream_type", "provider")
    search_fields = ("completed_activity__provider_activity_id", "provider")
    readonly_fields = ("created_at",)
    raw_id_fields = ("completed_activity",)


# ==============================================================================
#  PR-118: Plan vs Real Reconciliation
# ==============================================================================

@admin.register(WorkoutReconciliation)
class WorkoutReconciliationAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "organization",
        "state",
        "compliance_score",
        "compliance_category",
        "primary_target_used",
        "match_method",
        "match_confidence",
        "reconciled_at",
    )
    list_filter = ("organization", "state", "compliance_category", "match_method")
    search_fields = (
        "assignment__planned_workout__name",
        "assignment__athlete__user__username",
        "notes",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "reconciled_at",
        "compliance_score",
        "compliance_category",
        "primary_target_used",
        "score_detail",
        "signals",
        "match_confidence",
    )
    raw_id_fields = ("assignment", "completed_activity")