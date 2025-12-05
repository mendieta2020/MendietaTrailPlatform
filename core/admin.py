from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin import helpers 
import nested_admin  # <--- IMPORTANTE: Importamos la librería para anidar

# Importamos tus modelos, servicios y TAREAS (Nuevo)
from .models import (
    Alumno, PlantillaEntrenamiento, BloqueEntrenamiento, 
    PasoEntrenamiento, Entrenamiento, 
    Carrera, InscripcionCarrera,
    Actividad # <--- NUEVO MODELO IMPORTADO
)
from .services import asignar_plantilla_a_alumno
from .tasks import procesar_metricas_entrenamiento # <--- IMPORTANTE: El Ejecutor

# ==============================================================================
#  1. CONFIGURACIÓN VISUAL AVANZADA (NESTED INLINES)
# ==============================================================================

# Formulario para mejorar el aspecto de los inputs
class PasoInlineForm(forms.ModelForm):
    class Meta:
        model = PasoEntrenamiento
        fields = '__all__'
        widgets = {
            'titulo_paso': forms.TextInput(attrs={'style': 'width: 250px;', 'placeholder': 'Ej: Trote suave'}),
            'nota_paso': forms.TextInput(attrs={'style': 'width: 200px;', 'placeholder': 'Notas clave...'}),
            'valor_duracion': forms.NumberInput(attrs={'style': 'width: 70px;'}),
            'orden': forms.NumberInput(attrs={'style': 'width: 50px; text-align: center;'}),
        }

# CAMBIO 1: Usamos NestedTabularInline
class PasoInline(nested_admin.NestedTabularInline):
    model = PasoEntrenamiento
    form = PasoInlineForm
    extra = 0 
    min_num = 1 
    fk_name = 'bloque' # Asegura la relación correcta
    sortable_field_name = "orden"
    
    fields = ('orden', 'fase', 'valor_duracion', 'unidad_duracion', 'objetivo', 'titulo_paso', 'nota_paso')
    
    verbose_name = "👟 Paso del Ejercicio"
    verbose_name_plural = "👟 DETALLE DE LOS PASOS"
    
    classes = ['collapse'] 

# CAMBIO 2: Usamos NestedStackedInline y metemos los Pasos ADENTRO
class BloqueInline(nested_admin.NestedStackedInline):
    model = BloqueEntrenamiento
    extra = 0
    verbose_name = "🔁 BLOQUE / SECUENCIA"
    verbose_name_plural = "🏗️ ESTRUCTURA DE LA SESIÓN (Define los bloques aquí)"
    sortable_field_name = "orden"
    
    fieldsets = (
        (None, {
            'fields': (('orden', 'nombre_bloque', 'repeticiones'),)
        }),
    )
    
    # ¡AQUÍ ESTÁ LA MAGIA! Esto permite editar pasos dentro del bloque sin salir
    inlines = [PasoInline]

# ==============================================================================
#  2. ACCIÓN DE ASIGNACIÓN MASIVA (Tu lógica original)
# ==============================================================================

class AsignarForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    alumno = forms.ModelChoiceField(queryset=Alumno.objects.all(), label="Selecciona el Alumno")
    fecha = forms.DateField(widget=forms.SelectDateWidget, label="Fecha de Ejecución")

def asignar_a_alumno_action(modeladmin, request, queryset):
    if 'apply' in request.POST:
        form = AsignarForm(request.POST)
        if form.is_valid():
            alumno = form.cleaned_data['alumno']
            fecha = form.cleaned_data['fecha']
            creados = 0
            
            for plantilla in queryset:
                if plantilla.bloques.count() == 0:
                    modeladmin.message_user(request, f"⚠️ {plantilla.titulo}: Vacía (sin bloques).", level=messages.ERROR)
                    continue
                
                asignar_plantilla_a_alumno(plantilla, alumno, fecha)
                creados += 1
            
            if creados > 0:
                modeladmin.message_user(request, f"✅ ¡Éxito! {creados} entrenamientos asignados a {alumno}.", level=messages.SUCCESS)
            return redirect(request.get_full_path())
    else:
        form = AsignarForm(initial={'_selected_action': request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)})

    return render(request, 'admin/asignar_plantilla.html', {
        'items': queryset, 'form': form, 'title': 'Asignar Plantilla'
    })

asignar_a_alumno_action.short_description = "🚀 Asignar a Alumno (Copiar al Calendario)"

# ==============================================================================
#  3. ACCIÓN DE CÁLCULO DE MÉTRICAS (NUEVO - FASE 5.C)
# ==============================================================================

@admin.action(description="⚡ Calcular Métricas (TSS / TRIMP / Load)")
def calcular_metricas_action(modeladmin, request, queryset):
    """
    Recorre los entrenamientos seleccionados y ejecuta el cálculo fisiológico.
    """
    conteo = 0
    errores = 0
    for entreno in queryset:
        # En producción usaríamos .delay() de Celery. Aquí llamamos directo para ver el resultado ya.
        try:
            resultado = procesar_metricas_entrenamiento(entreno.id)
            if "OK" in resultado:
                conteo += 1
            else:
                errores += 1
        except Exception:
            errores += 1
            
    mensaje = f"✅ Se recalcularon las métricas de {conteo} entrenamientos."
    if errores > 0:
        mensaje += f" (Hubo {errores} fallos o saltos por falta de datos)."
    
    nivel = messages.SUCCESS if errores == 0 else messages.WARNING
    modeladmin.message_user(request, mensaje, level=nivel)

# ==============================================================================
#  4. PANELES PRINCIPALES (Vistas de Lista y Edición)
# ==============================================================================

# CAMBIO 3: Usamos NestedModelAdmin para que soporte la anidación
@admin.register(PlantillaEntrenamiento)
class PlantillaAdmin(nested_admin.NestedModelAdmin):
    # Vista de Lista
    list_display = ('get_emoji_deporte', 'titulo', 'get_dificultad_visual', 'ver_estructura', 'acciones')
    list_display_links = ('titulo',)
    list_filter = ('deporte', 'etiqueta_dificultad')
    search_fields = ('titulo', 'descripcion_global')
    actions = [asignar_a_alumno_action]
    list_per_page = 20

    # Vista de Edición
    fieldsets = (
        ('ENCABEZADO', {
            'fields': (('titulo', 'deporte'), ('etiqueta_dificultad', 'enlace_video')),
            'description': 'Datos generales de la sesión.'
        }),
        ('CONTENIDO', {
            'fields': ('descripcion_global',),
            'classes': ('wide',),
        }),
    )
    
    # Esto renderiza Bloques y Pasos en cascada
    inlines = [BloqueInline]

    # --- Decoradores Visuales ---
    def ver_estructura(self, obj):
        bloques = obj.bloques.count()
        return f"{bloques} Bloques"
    ver_estructura.short_description = "Estructura"

    def acciones(self, obj):
        url = reverse('admin:core_plantillaentrenamiento_change', args=[obj.id])
        return format_html(f'<a href="{url}" class="button" style="background:#3b82f6; color:white; padding:4px 10px; border-radius:4px;">✏️ Editar</a>')

# --- EDITOR DE BLOQUES INDIVIDUAL (Opcional, pero útil) ---
@admin.register(BloqueEntrenamiento)
class BloqueAdmin(nested_admin.NestedModelAdmin):
    list_display = ('plantilla', 'orden', 'resumen', 'conteo_pasos')
    
    def get_fields(self, request, obj=None):
        if obj and obj.entrenamiento:
            return (('entrenamiento', 'orden'), ('nombre_bloque', 'repeticiones'))
        return (('plantilla', 'orden'), ('nombre_bloque', 'repeticiones'))

    # También permitimos editar pasos aquí
    inlines = [PasoInline]

    def resumen(self, obj):
        return f"{obj.nombre_bloque} (x{obj.repeticiones})"
    def conteo_pasos(self, obj):
        return obj.pasos.count()

# --- ENTRENAMIENTO REAL (Calendario) ---
# CAMBIO 4: También lo hacemos Nested para ver la estructura del alumno
@admin.register(Entrenamiento)
class EntrenamientoAdmin(nested_admin.NestedModelAdmin):
    # Agregamos 'ver_carga' para visualizar el resultado del cálculo
    list_display = ('fecha_asignada', 'alumno', 'titulo', 'completado_visual', 'ver_carga') 
    list_filter = ('fecha_asignada', 'completado', 'alumno')
    search_fields = ('titulo', 'alumno__nombre', 'alumno__apellido')
    date_hierarchy = 'fecha_asignada'
    
    # Agregamos la nueva acción al menú desplegable
    actions = [calcular_metricas_action]
    
    # Permite ver y editar la estructura completa del alumno
    inlines = [BloqueInline]

    # Campos de solo lectura para las métricas (para que nadie las edite a mano por error)
    readonly_fields = ('tss', 'trimp', 'intensity_factor', 'load_final', 'kilojoules', 'created_at')

    # Organización visual en el formulario de edición
    fieldsets = (
        ('Datos Principales', {
            'fields': (('alumno', 'fecha_asignada'), ('titulo', 'completado'), 'plantilla_origen')
        }),
        ('Ejecución Real (Inputs)', {
            'fields': (('tiempo_real_min', 'distancia_real_km', 'desnivel_real_m'), 
                       ('potencia_promedio', 'frecuencia_cardiaca_promedio', 'rpe')),
            'description': 'Datos sincronizados desde Strava o ingresados manualmente.'
        }),
        ('Métricas Fisiológicas (Outputs)', {
            'fields': (('load_final', 'tss', 'trimp'), ('intensity_factor', 'kilojoules')),
            'classes': ('collapse',),
            'description': 'Calculado automáticamente por el algoritmo.'
        }),
        ('Otros', {
            'fields': ('feedback_alumno', ('strava_id', 'garmin_id')),
            'classes': ('collapse',)
        })
    )

    def completado_visual(self, obj):
        color = 'green' if obj.completado else 'red'
        icon = '✅' if obj.completado else '⏳'
        return format_html(f'<span style="color:{color};">{icon}</span>')
    completado_visual.short_description = "Estado"

    # Columna visual para ver la carga calculada
    def ver_carga(self, obj):
        if obj.load_final:
            # Mostramos en negrita el Load Final y detalles en gris
            return format_html(
                '<span style="font-size:1.1em; font-weight:bold; color:#2c3e50;">{}</span> '
                '<span style="color:#7f8c8d; font-size:0.9em;">(TSS:{} | TRIMP:{})</span>',
                obj.load_final, 
                int(obj.tss) if obj.tss else "-", 
                int(obj.trimp) if obj.trimp else "-"
            )
        return format_html('<span style="color:#bdc3c7;">-</span>')
    ver_carga.short_description = "Carga (Load)"

# --- OTROS (Sin cambios mayores, solo Admin estándar) ---
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    # Agregamos los campos nuevos al admin de alumnos
    list_display = ('nombre', 'apellido', 'categoria', 'ftp', 'ciudad')
    search_fields = ('nombre', 'apellido')
    fieldsets = (
        ('Información Personal', {
            'fields': (('nombre', 'apellido'), ('email', 'telefono'), 'ciudad', 'fecha_nacimiento')
        }),
        ('Datos Físicos', {
            'fields': (('peso', 'altura'), 'categoria')
        }),
        ('Perfil de Rendimiento (Zones)', {
            'fields': (('ftp', 'fcm', 'fcreposo'),),
            'description': 'Datos críticos para el cálculo de métricas (TSS, TRIMP).'
        }),
    )

@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'fecha', 'distancia_km')

@admin.register(InscripcionCarrera)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'carrera', 'estado')

# --- 6. ADMIN DE PERSISTENCIA (STRAVA / EXTERNO) - FASE 8 ---
@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'usuario', 'fecha_inicio', 'distancia', 'tipo_deporte', 'strava_id')
    list_filter = ('tipo_deporte', 'fecha_inicio', 'usuario')
    search_fields = ('nombre', 'strava_id', 'usuario__username')
    readonly_fields = ('creado_en', 'datos_brutos') # Protegemos los datos crudos