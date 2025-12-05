from django.db import models
from django.contrib.auth.models import User  # <--- NUEVO IMPORT NECESARIO
from django.utils.html import format_html

# --- 1. CONFIGURACIÓN Y CONSTANTES ---

TIPO_ACTIVIDAD = [
    ('RUN', 'Running (Calle)'), ('TRAIL', 'Trail Running (Montaña)'),
    ('CYCLING', 'Ciclismo / Ruta'), ('MTB', 'Ciclismo / MTB'),
    ('SWIMMING', 'Natación'), ('STRENGTH', 'Fuerza / Gimnasio'),
    ('CARDIO', 'Cardio / Funcional'), ('INDOOR_BIKE', 'Bici Fija / Rodillo'),
    ('REST', 'Descanso Total'), ('OTHER', 'Otro'),
]

FASE_PASO = [
    ('WARMUP', '🔥 Calentamiento'), ('ACTIVE', '⚡ Activo / Intervalo'),
    ('RECOVERY', '💤 Recuperación'), ('COOLDOWN', '❄️ Vuelta a la calma'),
    ('OTHER', '📝 Nota Técnica'),
]

TIPO_DURACION = [
    ('DISTANCE', 'Distancia'), ('TIME', 'Tiempo'),
    ('LAP_BUTTON', 'Presionar Lap'), ('CALORIES', 'Calorías'),
    ('OPEN', 'Abierto / Sin límite'),
]

UNIDAD_MEDIDA = [
    ('KM', 'km'), ('METERS', 'metros'),
    ('MIN', 'minutos'), ('SEC', 'segundos'),
]

TIPO_OBJETIVO = [
    ('NONE', 'Sin Objetivo'),
    ('RPE_1', '1 - Muy Suave (Recuperación)'), ('RPE_2', '2 - Suave (Aeróbico Extensivo)'),
    ('RPE_3', '3 - Moderado (Aeróbico Medio)'), ('RPE_4', '4 - Ritmo Maratón'),
    ('RPE_5', '5 - Umbral Anaeróbico'), ('RPE_6', '6 - VO2 Max'),
    ('RPE_7', '7 - Capacidad Anaeróbica'), ('RPE_8', '8 - Sprint'),
    ('RPE_9', '9 - Neuromuscular'), ('RPE_10', '10 - Máximo Esfuerzo'),
    ('ZONA_FC', 'Zona Frecuencia Cardíaca'), ('PACE', 'Ritmo Objetivo'),
]

ZONA_INTENSIDAD = [
    ('Z1', 'Z1 - Recuperación'), ('Z2', 'Z2 - Aeróbico Base'),
    ('Z3', 'Z3 - Ritmo Tempo'), ('Z4', 'Z4 - Umbral Lactato'),
    ('Z5', 'Z5 - VO2 Max'), ('Z6', 'Z6 - Anaeróbico'), ('Z7', 'Z7 - Neuromuscular'),
]

# --- 2. MODELOS PRINCIPALES ---

class Alumno(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    ciudad = models.CharField(max_length=50, null=True, blank=True)
    peso = models.FloatField(help_text="Peso en Kg")
    altura = models.FloatField(help_text="Altura en Metros (ej: 1.75)")
    fecha_nacimiento = models.DateField()
    CATEGORIAS = [('K21', '21K'), ('K42', '42K'), ('ULTRA', 'Ultra')]
    categoria = models.CharField(max_length=10, choices=CATEGORIAS, default='K21')

    # --- NUEVOS CAMPOS FISIOLÓGICOS (FASE 5.C) ---
    ftp = models.IntegerField(default=200, help_text="Potencia Umbral Funcional (Watts)")
    fcm = models.IntegerField(default=180, help_text="Frecuencia Cardíaca Máxima")
    fcreposo = models.IntegerField(default=50, help_text="Frecuencia Cardíaca en Reposo")
    # ---------------------------------------------

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

class PlantillaEntrenamiento(models.Model):
    titulo = models.CharField(max_length=200, help_text="Ej: Series 10x400m + Umbral")
    deporte = models.CharField(max_length=20, choices=TIPO_ACTIVIDAD, default='RUN')
    descripcion_global = models.TextField(blank=True, help_text="Descripción completa, enlaces, estrategia. ¡Usa emojis! 🚴‍♂️🏃‍♀️")
    enlace_video = models.URLField(blank=True, null=True, help_text="Link a YouTube/Vimeo explicativo")
    DIFICULTADES = [('EASY', '🟢 Suave'), ('MODERATE', '🟡 Moderado'), ('HARD', '🔴 Duro'), ('EXTREME', '⚫ Extremo')]
    etiqueta_dificultad = models.CharField(max_length=20, choices=DIFICULTADES, default='MODERATE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "📂 Plantilla de Librería"
        verbose_name_plural = "Librería de Entrenamientos"

    def __str__(self):
        return f"{self.titulo}"

    def get_emoji_deporte(self):
        emojis = {'RUN': '🏃‍♂️', 'TRAIL': '⛰️🏃‍♂️', 'CYCLING': '🚴‍♂️', 'MTB': '🚵‍♂️', 'SWIMMING': '🏊‍♂️', 'STRENGTH': '🏋️‍♂️', 'CARDIO': '🤸‍♂️', 'INDOOR_BIKE': '🚴‍♀️🏠', 'REST': '🛌', 'OTHER': '⚙️'}
        return emojis.get(self.deporte, '❓')
    get_emoji_deporte.short_description = 'Tipo'

    def get_dificultad_visual(self):
        colores = {'EASY': '#28a745', 'MODERATE': '#ffc107', 'HARD': '#dc3545', 'EXTREME': '#343a40'}
        color = colores.get(self.etiqueta_dificultad, '#6c757d')
        return format_html('<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 10px; font-weight: bold; font-size: 0.8em;">{}</span>', color, self.get_etiqueta_dificultad_display())
    get_dificultad_visual.short_description = 'Dificultad'

# --- 3. MODELO DE ASIGNACIÓN (El Calendario) ---

class Entrenamiento(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='entrenamientos')
    plantilla_origen = models.ForeignKey(PlantillaEntrenamiento, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_asignada = models.DateField()
    titulo = models.CharField(max_length=200)
    completado = models.BooleanField(default=False)
    
    # Feedback y Datos Reales
    distancia_real_km = models.FloatField(null=True, blank=True)
    tiempo_real_min = models.IntegerField(null=True, blank=True)
    desnivel_real_m = models.IntegerField(null=True, blank=True)
    
    # --- INPUTS PARA CÁLCULO (FASE 5.C) ---
    potencia_promedio = models.IntegerField(null=True, blank=True, help_text="Vatios medios (Avg Watts)")
    frecuencia_cardiaca_promedio = models.IntegerField(null=True, blank=True, help_text="Pulsaciones medias (Avg HR)")
    # --------------------------------------

    rpe = models.IntegerField(null=True, blank=True)
    feedback_alumno = models.TextField(null=True, blank=True)
    strava_id = models.CharField(max_length=50, blank=True, null=True)
    garmin_id = models.CharField(max_length=50, blank=True, null=True)
    
    # --- RESULTADOS MÉTRICAS CALCULADAS (FASE 5.C) ---
    tss = models.FloatField(null=True, blank=True, help_text="Training Stress Score (Carga de Potencia)")
    trimp = models.FloatField(null=True, blank=True, help_text="Training Impulse (Carga Cardíaca)")
    intensity_factor = models.FloatField(null=True, blank=True, help_text="IF: Intensidad relativa al FTP")
    normalized_power = models.IntegerField(null=True, blank=True, help_text="NP: Potencia Normalizada estimada")
    kilojoules = models.IntegerField(null=True, blank=True, help_text="Trabajo total realizado")
    
    load_final = models.FloatField(null=True, blank=True, help_text="Carga Final (Prioridad: TSS > TRIMP > RPE)")
    # -------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_asignada']

    def __str__(self):
        return f"{self.fecha_asignada} - {self.titulo} ({self.alumno})"

# --- 4. ESTRUCTURA (BLOQUES Y PASOS) ---

class BloqueEntrenamiento(models.Model):
    plantilla = models.ForeignKey(PlantillaEntrenamiento, related_name='bloques', on_delete=models.CASCADE, null=True, blank=True)
    entrenamiento = models.ForeignKey(Entrenamiento, related_name='bloques_reales', on_delete=models.CASCADE, null=True, blank=True)
    orden = models.PositiveIntegerField(default=1)
    nombre_bloque = models.CharField(max_length=100, default="Bloque Estándar", blank=True) 
    repeticiones = models.PositiveIntegerField(default=1, help_text="Repeticiones de este bloque")

    class Meta:
        ordering = ['orden']
        verbose_name = "Estructura"
        verbose_name_plural = "Estructura"

    def __str__(self):
        return f"Bloque {self.orden}"

class PasoEntrenamiento(models.Model):
    bloque = models.ForeignKey(BloqueEntrenamiento, related_name='pasos', on_delete=models.CASCADE)
    orden = models.PositiveIntegerField(default=1)
    fase = models.CharField(max_length=20, choices=FASE_PASO, default='ACTIVE', verbose_name="Tipo")
    
    # --- CAMPO INTEGRADO CORRECTAMENTE ---
    tipo_duracion = models.CharField(max_length=20, choices=TIPO_DURACION, default='TIME', verbose_name="Tipo Duración") 
    
    titulo_paso = models.CharField(max_length=100, blank=True, verbose_name="Descripción")
    
    # --- CAMPOS DE DATOS ---
    valor_duracion = models.FloatField(default=0, verbose_name="Cantidad")
    unidad_duracion = models.CharField(max_length=10, choices=UNIDAD_MEDIDA, default='KM', verbose_name="Unidad")
    objetivo = models.CharField(max_length=20, choices=TIPO_OBJETIVO, default='RPE_2', verbose_name="Intensidad")
    nota_paso = models.CharField(max_length=200, blank=True, help_text="Nota extra")

    class Meta:
        ordering = ['orden']
        verbose_name = "Paso"
        verbose_name_plural = "Pasos del Bloque"

    def __str__(self):
        return f"{self.orden}. {self.titulo_paso}"

# --- MÓDULO DE COMPETICIONES Y EVENTOS ---

TIPO_CARRERA = [
    ('TRAIL', 'Trail Running'),
    ('ULTRA', 'Ultra Distancia'),
    ('CALLE', 'Calle / Asfalto'),
    ('CICLISMO', 'Ciclismo'),
    ('TRIATLON', 'Triatlón'),
    ('AVENTURA', 'Carrera de Aventura'),
    ('OTRO', 'Otro Evento'),
]

class Carrera(models.Model):
    nombre = models.CharField(max_length=200, help_text="Ej: Patagonia Run 2025")
    tipo = models.CharField(max_length=20, choices=TIPO_CARRERA, default='TRAIL')
    fecha = models.DateField()
    lugar = models.CharField(max_length=100, blank=True, help_text="Ciudad / Provincia")
    distancia_km = models.FloatField(help_text="Distancia total")
    desnivel_positivo_m = models.IntegerField(default=0, help_text="Metros acumulados (+)")
    web_oficial = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.fecha.year})"

class InscripcionCarrera(models.Model):
    ESTADOS = [
        ('INSCRITO', '✅ Inscrito'),
        ('INTERESADO', '👀 Interesado / Objetivo Posible'),
        ('BAJA', '❌ Baja / No corre'),
        ('FINALIZADO', '🏅 Finalizó'),
        ('DNF', '💀 Abandonó (DNF)'),
    ]

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='carreras')
    carrera = models.ForeignKey(Carrera, on_delete=models.CASCADE, related_name='inscriptos')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='INSCRITO')
    prioridad = models.CharField(max_length=1, choices=[('A', 'A - Principal'), ('B', 'B - Preparatoria'), ('C', 'C - Entrenamiento')], default='A', help_text="Importancia de la carrera")
    tiempo_oficial = models.DurationField(null=True, blank=True, help_text="Tiempo final hh:mm:ss")
    posicion_general = models.IntegerField(null=True, blank=True)
    posicion_categoria = models.IntegerField(null=True, blank=True)
    feedback_carrera = models.TextField(blank=True, help_text="Análisis post-carrera del alumno")

    class Meta:
        unique_together = ('alumno', 'carrera')
        verbose_name = "🏅 Inscripción / Objetivo"
        verbose_name_plural = " Calendario de Carreras"

    def __str__(self):
        return f"{self.alumno} -> {self.carrera}"

# --- 6. MODELO DE PERSISTENCIA (STRAVA / EXTERNO) - FASE 8 ---
class Actividad(models.Model):
    # Vinculamos la actividad al usuario de Django (el dueño de la cuenta Strava)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='actividades_strava')
    
    # ID único de Strava (Evita guardar la misma carrera dos veces)
    strava_id = models.BigIntegerField(unique=True, help_text="ID único de la actividad en Strava")
    
    # Datos básicos
    nombre = models.CharField(max_length=255)
    distancia = models.FloatField(help_text="Distancia en metros")
    tiempo_movimiento = models.IntegerField(help_text="Tiempo en segundos")
    fecha_inicio = models.DateTimeField(help_text="Fecha y hora de inicio (Local)")
    tipo_deporte = models.CharField(max_length=50, help_text="Run, Ride, Swim, etc.")
    
    # Datos avanzados (opcionales por ahora, pero listos para el futuro)
    desnivel_positivo = models.FloatField(default=0.0, null=True, blank=True)
    ritmo_promedio = models.FloatField(help_text="Metros por segundo", null=True, blank=True)
    mapa_polilinea = models.TextField(null=True, blank=True, help_text="Código del mapa para dibujar")
    
    # JSON Crudo: Guardamos TODO lo que manda Strava por si queremos datos raros a futuro
    datos_brutos = models.JSONField(default=dict, blank=True)

    # Auditoría interna
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Actividad Importada"
        verbose_name_plural = "Actividades Importadas"
        ordering = ['-fecha_inicio'] # Las más nuevas primero

    def __str__(self):
        return f"{self.nombre} ({self.distancia:.0f}m) - {self.usuario.username}"