from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from datetime import date, timedelta
from django.db.models import Sum, Q
from django.utils import timezone
import uuid

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
    # Multi-tenant (coach-scoped): el uploader define el tenant
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="videos_ejercicios",
        null=True,
        blank=True,
        db_index=True,
    )
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
    # Multi-tenant (coach-scoped): un equipo pertenece a un entrenador (permite equipos vacíos seguros)
    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="equipos",
        null=True,
        blank=True,
        db_index=True,
    )
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
        constraints = [
            # Strava activity id es globalmente único, pero el campo permite NULL/blank.
            # Este índice parcial previene duplicados reales sin romper registros legacy.
            models.UniqueConstraint(
                fields=["strava_id"],
                condition=Q(strava_id__isnull=False) & ~Q(strava_id=""),
                name="uniq_entrenamiento_strava_id_not_blank",
            ),
        ]

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
    """
    Actividad interna unificada (fuente de verdad del "actual").

    Diseñada para soportar múltiples fuentes (Strava hoy, Garmin/Coros/Suunto después).
    - Idempotencia: (source, source_object_id) evita duplicados multi-provider.
    - `datos_brutos` (raw_json) se mantiene para auditoría y cálculos futuros.
    - `strava_id` queda como campo legacy/compat (solo para source=strava).
    """

    class Validity(models.TextChoices):
        VALID = "VALID", "VALID"
        DISCARDED = "DISCARDED", "DISCARDED"

    class Source(models.TextChoices):
        STRAVA = "strava", "strava"
        GARMIN = "garmin", "garmin"
        COROS = "coros", "coros"
        SUUNTO = "suunto", "suunto"
        MANUAL = "manual", "manual"
        OTHER = "other", "other"

    # Coach propietario del token usado para importar (tenant)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="actividades_strava",
        db_index=True,
    )
    # Alumno/atleta dueño real de la actividad (multi-tenant correcto)
    alumno = models.ForeignKey(
        "Alumno",
        on_delete=models.CASCADE,
        related_name="actividades",
        null=True,
        blank=True,
        db_index=True,
    )

    # Multi-fuente (nuevo): clave idempotente de la actividad en su provider de origen.
    # Ej: source=strava, source_object_id="123456789"
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.STRAVA, db_index=True)
    source_object_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    # Hash opcional para detectar cambios de payload sin comparar JSON completo.
    source_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # Legacy/compat: ID numérico Strava (solo para source=strava). No usar para otros providers.
    strava_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    nombre = models.CharField(max_length=255)
    distancia = models.FloatField(help_text="Distancia en metros", default=0.0)
    tiempo_movimiento = models.IntegerField(help_text="Tiempo en segundos", default=0)
    fecha_inicio = models.DateTimeField()
    tipo_deporte = models.CharField(max_length=50)
    desnivel_positivo = models.FloatField(default=0.0)
    ritmo_promedio = models.FloatField(blank=True, null=True, help_text="Metros por segundo")

    # Auditoría / visualización
    mapa_polilinea = models.TextField(blank=True, null=True)
    datos_brutos = models.JSONField(default=dict, blank=True)

    # Validación estricta para UI/insights futuros
    validity = models.CharField(max_length=12, choices=Validity.choices, default=Validity.VALID)
    invalid_reason = models.CharField(max_length=120, blank=True, default="")

    # Nullables para poder reintroducirlos sin prompts de migración (backfill opcional).
    creado_en = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        ordering = ["-fecha_inicio"]
        indexes = [
            models.Index(fields=["usuario", "-fecha_inicio"]),
            models.Index(fields=["alumno", "-fecha_inicio"]),
        ]
        constraints = [
            # Idempotencia multi-fuente (evita duplicados si la actividad existe en el provider).
            models.UniqueConstraint(
                fields=["source", "source_object_id"],
                condition=Q(source_object_id__isnull=False) & ~Q(source_object_id=""),
                name="uniq_actividad_source_object_id_not_blank",
            ),
            # Compat: strava_id único solo cuando existe (permite futuras fuentes sin strava_id).
            models.UniqueConstraint(
                fields=["strava_id"],
                condition=Q(strava_id__isnull=False),
                name="uniq_actividad_strava_id_not_null",
            ),
        ]

    def __str__(self):
        if self.source == self.Source.STRAVA and self.strava_id is not None:
            return f"{self.nombre} (strava:{self.strava_id})"
        if self.source_object_id:
            return f"{self.nombre} ({self.source}:{self.source_object_id})"
        return f"{self.nombre} ({self.source})"

    def save(self, *args, **kwargs):
        # Backfill defensivo (compat): si es Strava y no está seteado source_object_id, lo derivamos.
        if not self.source:
            self.source = self.Source.STRAVA
        if self.source == self.Source.STRAVA and (not self.source_object_id) and self.strava_id is not None:
            self.source_object_id = str(self.strava_id)
        super().save(*args, **kwargs)


class StravaWebhookEvent(models.Model):
    """
    Evento de Webhook Strava (idempotencia + auditoría).

    El endpoint de webhook debe crear este registro y encolar el procesamiento.
    Si el mismo evento llega dos veces, el UniqueConstraint en `event_uid` evita reprocesarlo.
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "received"
        QUEUED = "queued", "queued"
        PROCESSING = "processing", "processing"
        PROCESSED = "processed", "processed"
        DISCARDED = "discarded", "discarded"
        IGNORED = "ignored", "ignored"
        FAILED = "failed", "failed"

    # Normalización multi-provider (hoy solo Strava, pero dejamos el shape SaaS)
    provider = models.CharField(max_length=20, default="strava", db_index=True)
    # Strava no envía event_id canónico; dejamos campo para futuros providers/compat.
    provider_event_id = models.CharField(max_length=120, blank=True, default="", db_index=True)

    # Correlación (uuid) para logging/tracing cross-systems
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)

    event_uid = models.CharField(max_length=80, unique=True, db_index=True)

    object_type = models.CharField(max_length=40, db_index=True)
    object_id = models.BigIntegerField(db_index=True)
    aspect_type = models.CharField(max_length=20, db_index=True)
    owner_id = models.BigIntegerField(db_index=True)
    subscription_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    # Strava canonical: unix epoch (segundos) del evento.
    event_time = models.BigIntegerField(null=True, blank=True, db_index=True)

    payload_raw = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    # Estado final requerido (por qué se descartó / mensaje de error “humano”)
    discard_reason = models.CharField(max_length=160, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)

    processed_at = models.DateTimeField(null=True, blank=True)
    # Referencia opcional al resultado del pipeline (Actividad interna).
    actividad = models.ForeignKey(
        "Actividad",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="strava_webhook_events",
        db_index=True,
    )
    # Métrica operativa: cuántas veces llegó el mismo evento (dedupe por constraint).
    duplicate_count = models.PositiveIntegerField(default=0)
    last_duplicate_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner_id", "-received_at"]),
            models.Index(fields=["status", "-received_at"]),
            models.Index(fields=["object_type", "aspect_type", "object_id"]),
            models.Index(fields=["provider", "provider_event_id"]),
        ]
        constraints = [
            # Requerimiento Fase 4: UniqueConstraint explícito para idempotencia y carreras.
            models.UniqueConstraint(fields=["provider", "event_uid"], name="uniq_strava_provider_event_uid"),
        ]

    def mark_processed(self):
        self.status = self.Status.PROCESSED
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at"])

    def mark_discarded(self, *, reason: str):
        self.status = self.Status.DISCARDED
        self.discard_reason = str(reason or "")
        self.processed_at = timezone.now()
        self.error_message = ""
        self.save(update_fields=["status", "discard_reason", "processed_at", "error_message"])


class StravaImportLog(models.Model):
    """
    Log de ingesta por actividad/evento (auditoría "perfecta" para debugging y UI futura).
    """

    class Status(models.TextChoices):
        FETCHED = "fetched", "fetched"
        SAVED = "saved", "saved"
        DISCARDED = "discarded", "discarded"
        FAILED = "failed", "failed"

    event = models.ForeignKey(StravaWebhookEvent, on_delete=models.CASCADE, related_name="import_logs", db_index=True)
    alumno = models.ForeignKey("Alumno", on_delete=models.SET_NULL, null=True, blank=True, related_name="strava_import_logs", db_index=True)
    actividad = models.ForeignKey("Actividad", on_delete=models.SET_NULL, null=True, blank=True, related_name="strava_import_logs", db_index=True)

    strava_activity_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    attempt = models.PositiveSmallIntegerField(default=0)

    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    reason = models.CharField(max_length=160, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["strava_activity_id", "-created_at"]),
            models.Index(fields=["alumno", "-created_at"]),
            models.Index(fields=["event", "-created_at"]),
        ]


class StravaActivitySyncState(models.Model):
    """
    Lock/estado por actividad para evitar pipelines simultáneos (dedupe robusto).

    Este modelo NO reemplaza `Actividad` (dato de negocio), solo coordina concurrencia
    y guarda el resultado de la ingesta por `strava_activity_id`.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "running"
        SUCCEEDED = "succeeded", "succeeded"
        DISCARDED = "discarded", "discarded"
        FAILED = "failed", "failed"

    provider = models.CharField(max_length=20, default="strava", db_index=True)
    athlete_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    strava_activity_id = models.BigIntegerField(db_index=True)

    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_by_event_uid = models.CharField(max_length=80, blank=True, default="", db_index=True)

    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, default="")
    discard_reason = models.CharField(max_length=160, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "strava_activity_id"],
                name="uniq_strava_provider_activity_id",
            ),
        ]
        indexes = [
            models.Index(fields=["athlete_id", "-updated_at"]),
            models.Index(fields=["status", "-updated_at"]),
        ]

@receiver(post_save, sender=Pago)
def actualizar_pago_alumno(sender, instance, **kwargs):
    if instance.es_valido:
        alumno = instance.alumno
        if not alumno.fecha_ultimo_pago or instance.fecha_pago > alumno.fecha_ultimo_pago:
            alumno.fecha_ultimo_pago = instance.fecha_pago
            alumno.save()