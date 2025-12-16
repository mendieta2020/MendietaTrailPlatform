from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from datetime import date, timedelta
from django.db.models import Sum

# ==============================================================================
#  1. CONFIGURACIÓN Y CONSTANTES (GLOBALES)
# ==============================================================================

# --- CONSTANTES DE NEGOCIO ---
ESTADOS_ALUMNO = [
    ('ACTIVO', '✅ Activo (Entrenando)'),
    ('LESIONADO', '🚑 Inactivo (Lesión)'),
    ('PAUSA', '⏸️ Inactivo (Temporal/Vacaciones)'),
    ('DEUDA', '💰 Inactivo (Falta de Pago)'),
    ('BAJA', '❌ Baja Definitiva')
]

METODOS_PAGO = [
    ('TRANSFERENCIA', '🏦 Transferencia Bancaria'),
    ('EFECTIVO', '💵 Efectivo'),
    ('TARJETA', '💳 Tarjeta / Suscripción (Stripe/MP)'),
    ('BONIFICADO', '🎁 Becado / Canje')
]

TIPO_ACTIVIDAD = [
    ('RUN', 'Running (Calle)'), ('TRAIL', 'Trail Running (Montaña)'),
    ('CYCLING', 'Ciclismo / Ruta'), ('MTB', 'Ciclismo / MTB'),
    ('SWIMMING', 'Natación'), ('STRENGTH', 'Fuerza / Gimnasio'),
    ('CARDIO', 'Cardio / Funcional'), ('INDOOR_BIKE', 'Bici Fija / Rodillo'),
    ('REST', 'Descanso Total'), ('OTHER', 'Otro'),
]

INTENSIDAD_ZONAS = [('Z1', 'Z1 Recup'), ('Z2', 'Z2 Base'), ('Z3', 'Z3 Tempo'), ('Z4', 'Z4 Umbral'), ('Z5', 'Z5 VO2')]
TIPO_TERRENO = [
    (1.00, '🛣️ Asfalto / Pista'), (1.05, '🌲 Sendero Corrible'), 
    (1.15, '⛰️ Técnico Medio'), (1.25, '🧗 Técnico Duro'), (1.40, '🧟 Extremo')
]
TURNOS_DIA = [
    ('M', 'Mañana'), ('T', 'Tarde'), ('N', 'Noche'), 
    ('MT', 'Mañana/Tarde'), ('TN', 'Tarde/Noche'), ('FULL', 'Todo el Día'),
    ('NO', '❌ NO DISPONIBLE')
]

# ==============================================================================
#  2. MODELOS PRINCIPALES
# ==============================================================================

# --- NUEVO MODELO: VIDEOS DE EJERCICIOS (GIMNASIO PRO) ---
class VideoEjercicio(models.Model):
    titulo = models.CharField(max_length=100, blank=True, help_text="Ej: Sentadilla Técnica")
    archivo = models.FileField(upload_to='videos_ejercicios/', help_text="Soporta MP4, MOV, GIF")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "🎥 Video de Ejercicio"
        verbose_name_plural = "🎥 Videos de Ejercicios"

    def __str__(self):
        return f"Video {self.id}: {self.titulo or 'Sin Título'}"

# --- EQUIPOS (CLUSTERS DE ENTRENAMIENTO) ---
class Equipo(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Inicial Calle, Avanzado Montaña")
    descripcion = models.TextField(blank=True, null=True)
    color_identificador = models.CharField(max_length=7, default="#F57C00", help_text="Color Hexadecimal para el calendario")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "🏆 Equipo / Grupo"
        verbose_name_plural = "🏆 Equipos"

    def __str__(self):
        return self.nombre

    @property
    def cantidad_alumnos(self):
        return self.alumnos.count()

class Alumno(models.Model):
    entrenador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alumnos', null=True, blank=True)
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_alumno', null=True, blank=True)
    
    # --- VINCULACIÓN A EQUIPO ---
    equipo = models.ForeignKey(
        Equipo, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='alumnos'
    )

    strava_athlete_id = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text="ID Strava")
    
    # --- DATOS PERSONALES ---
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    instagram = models.CharField(max_length=50, blank=True, help_text="Usuario sin @")
    ciudad = models.CharField(max_length=50, null=True, blank=True)
    
    # --- ESTADO Y FINANZAS ---
    estado_actual = models.CharField(max_length=20, choices=ESTADOS_ALUMNO, default='ACTIVO', verbose_name="Estado Actual")
    fecha_alta = models.DateField(auto_now_add=True)
    fecha_ultimo_pago = models.DateField(null=True, blank=True, verbose_name="📅 Último Pago")
    
    # Salud
    esta_lesionado = models.BooleanField(default=False)
    apto_medico_al_dia = models.BooleanField(default=False)
    
    # --- BIOMETRÍA ---
    peso = models.FloatField(help_text="Peso en Kg", default=70.0)
    altura = models.FloatField(help_text="Altura en Metros", default=1.70)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    CATEGORIAS = [('K21', '21K'), ('K42', '42K'), ('ULTRA', 'Ultra')]
    categoria = models.CharField(max_length=10, choices=CATEGORIAS, default='K21')
    
    # --- FISIOLOGÍA AVANZADA (Para cálculos de carga) ---
    fcm = models.IntegerField(default=180, help_text="FC Máxima")
    fcreposo = models.IntegerField(default=50, help_text="FC Reposo")
    vo2_max = models.FloatField(default=0, verbose_name="VO2 Máx (Calc)")
    vam_actual = models.FloatField(default=0, verbose_name="VAM (Calc)")
    ftp_ciclismo = models.IntegerField(default=0, verbose_name="FTP (Watts)") # Nuevo para triatletas
    
    # --- ZONAS DE ENTRENAMIENTO (Calculadas o Manuales) ---
    # Esto es clave para enviar entrenamientos estructurados a Garmin
    zonas_fc = models.JSONField(default=dict, blank=True, help_text="{'z1': [120, 135], 'z2': [136, 145]...}")
    zonas_velocidad = models.JSONField(default=dict, blank=True, help_text="Ritmos en seg/km")

    def __str__(self): return f"{self.nombre} {self.apellido}"

# --- MODELO PAGOS ---
class Pago(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='pagos')
    fecha_pago = models.DateField(default=date.today)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS_PAGO, default='TRANSFERENCIA')
    es_valido = models.BooleanField(default=False, verbose_name="✅ Validado")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_pago']

# --- PLANTILLAS DE ENTRENAMIENTO (LIBRERÍA) ---
class PlantillaEntrenamiento(models.Model):
    titulo = models.CharField(max_length=200)
    deporte = models.CharField(max_length=20, choices=TIPO_ACTIVIDAD, default='RUN')
    descripcion_global = models.TextField(blank=True) # Resumen visual
    
    # --- 🔥 ESTRUCTURA JSON (El Cerebro) ---
    # Aquí guardamos los bloques: Calentamiento, Series, etc. para Garmin/Frontend
    # Ejemplo: { "bloques": [ { "tipo": "WARMUP", "duracion": 600, "target": "Z1" } ] }
    estructura = models.JSONField(default=dict, blank=True)
    
    etiqueta_dificultad = models.CharField(max_length=20, choices=[('EASY', '🟢 Suave'), ('MODERATE', '🟡 Moderado'), ('HARD', '🔴 Duro')], default='MODERATE')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.titulo

# --- ENTRENAMIENTO (CALENDARIO) ---
class Entrenamiento(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='entrenamientos')
    plantilla_origen = models.ForeignKey(PlantillaEntrenamiento, on_delete=models.SET_NULL, null=True, blank=True)
    
    fecha_asignada = models.DateField()
    titulo = models.CharField(max_length=200)
    
    # Descripción simple (para notas rápidas del coach)
    descripcion_detallada = models.TextField(blank=True, null=True)
    
    # --- 🔥 ESTRUCTURA JSON PRO (La Clave de la Escalabilidad) ---
    # Al clonar la plantilla, copiamos su estructura aquí.
    # Esto permite editar el entrenamiento del alumno SIN afectar la plantilla original.
    # Y es lo que leerá la API de Garmin para subir el workout al reloj.
    estructura = models.JSONField(default=dict, blank=True)

    tipo_actividad = models.CharField(max_length=20, choices=TIPO_ACTIVIDAD, default='RUN')
    
    # Métricas Planificadas (Resumen para Analytics)
    distancia_planificada_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tiempo_planificado_min = models.IntegerField(null=True, blank=True)
    desnivel_planificado_m = models.IntegerField(null=True, blank=True)
    rpe_planificado = models.IntegerField(default=0)
    
    # Métricas Reales (Feedback del Atleta / Strava)
    completado = models.BooleanField(default=False)
    distancia_real_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tiempo_real_min = models.IntegerField(null=True, blank=True)
    desnivel_real_m = models.IntegerField(null=True, blank=True)
    rpe = models.IntegerField(null=True, blank=True, help_text="RPE Real sentido por el atleta")
    feedback_alumno = models.TextField(null=True, blank=True)
    
    # IDs Externos
    strava_id = models.CharField(max_length=50, blank=True, null=True)
    
    # Métricas Avanzadas (Carga)
    porcentaje_cumplimiento = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta: 
        ordering = ['-fecha_asignada']

    def __str__(self): return f"{self.fecha_asignada} - {self.titulo}"

    def save(self, *args, **kwargs):
        # Cálculo automático de cumplimiento al guardar
        if self.completado:
            ratio = 0
            if self.distancia_planificada_km and self.distancia_planificada_km > 0:
                # Convertimos a float para calcular, ya que Decimal puede dar problemas mixtos
                plan = float(self.distancia_planificada_km)
                real = float(self.distancia_real_km or 0)
                ratio = (real / plan) * 100
            elif self.tiempo_planificado_min and self.tiempo_planificado_min > 0:
                plan = self.tiempo_planificado_min
                real = self.tiempo_real_min or 0
                ratio = (real / plan) * 100
            
            self.porcentaje_cumplimiento = int(min(max(ratio, 0), 200))
        
        super().save(*args, **kwargs)

# --- MODELOS DEPRECATED (SE MANTIENEN POR SEGURIDAD DE MIGRACIÓN) ---
# En el futuro, eliminaremos BloqueEntrenamiento y PasoEntrenamiento
# ya que toda esa info ahora vive dentro del JSONField 'estructura'.
class BloqueEntrenamiento(models.Model):
    # Modelo Legacy - No usar para nuevo desarrollo
    plantilla = models.ForeignKey(PlantillaEntrenamiento, related_name='bloques_legacy', on_delete=models.CASCADE, null=True, blank=True)
    entrenamiento = models.ForeignKey('Entrenamiento', related_name='bloques_reales_legacy', on_delete=models.CASCADE, null=True, blank=True)
    orden = models.PositiveIntegerField(default=1)

class PasoEntrenamiento(models.Model):
    # Modelo Legacy - No usar para nuevo desarrollo
    bloque = models.ForeignKey(BloqueEntrenamiento, related_name='pasos_legacy', on_delete=models.CASCADE)
    orden = models.PositiveIntegerField(default=1)

# --- OTROS MODELOS (Carreras, Actividades, Signal) ---
class Carrera(models.Model):
    nombre = models.CharField(max_length=200)
    fecha = models.DateField()
    distancia_km = models.FloatField()
    desnivel_positivo_m = models.IntegerField(default=0)
    def __str__(self): return self.nombre

class InscripcionCarrera(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='carreras')
    carrera = models.ForeignKey(Carrera, on_delete=models.CASCADE, related_name='inscriptos')
    estado = models.CharField(max_length=20, default='INSCRITO')

class Actividad(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='actividades_strava')
    strava_id = models.BigIntegerField(unique=True)
    nombre = models.CharField(max_length=255)
    distancia = models.FloatField()
    tiempo_movimiento = models.IntegerField()
    fecha_inicio = models.DateTimeField()
    tipo_deporte = models.CharField(max_length=50)
    desnivel_positivo = models.FloatField(default=0.0)
    def __str__(self): return self.nombre

@receiver(post_save, sender=Pago)
def actualizar_pago_alumno(sender, instance, **kwargs):
    if instance.es_valido:
        alumno = instance.alumno
        if not alumno.fecha_ultimo_pago or instance.fecha_pago > alumno.fecha_ultimo_pago:
            alumno.fecha_ultimo_pago = instance.fecha_pago
            alumno.save()