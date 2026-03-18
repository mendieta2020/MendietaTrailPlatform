from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from datetime import date, timedelta
from django.db.models import Sum, Q
from django.utils import timezone
import logging
import uuid

# Re-export OAuth integration status model for compatibility (single source of truth is integration_models.py)
from .integration_models import OAuthIntegrationStatus  # noqa: F401
from .compliance import calcular_porcentaje_cumplimiento

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
    nombre = models.CharField(max_length=100, help_text="Ej: Inicial Calle, Avanzado Montaña")
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
        constraints = [
            models.UniqueConstraint(fields=["nombre", "entrenador"], name="unique_team_per_coach"),
        ]

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
    email = models.EmailField(null=True, blank=True)
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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "entrenador"], name="unique_student_email_per_coach"),
        ]

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
    # Multi-tenant (coach-scoped): owner de la plantilla
    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="plantillas_entrenamiento",
        null=True,
        blank=True,
        db_index=True,
    )
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

# --- VERSIONADO DE PLANTILLAS (HISTORIAL INMUTABLE) ---
class PlantillaEntrenamientoVersion(models.Model):
    plantilla = models.ForeignKey(
        PlantillaEntrenamiento,
        on_delete=models.CASCADE,
        related_name="versiones",
    )
    version = models.PositiveIntegerField()
    estructura = models.JSONField(default=dict, blank=True)
    descripcion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
        constraints = [
            models.UniqueConstraint(fields=["plantilla", "version"], name="unique_version_per_template"),
        ]

    def __str__(self):
        return f"{self.plantilla.titulo} v{self.version}"

# --- ENTRENAMIENTO (CALENDARIO) ---
class Entrenamiento(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='entrenamientos')
    plantilla_origen = models.ForeignKey(PlantillaEntrenamiento, on_delete=models.SET_NULL, null=True, blank=True)
    plantilla_version = models.ForeignKey(
        "PlantillaEntrenamientoVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entrenamientos",
    )
    
    fecha_asignada = models.DateField()
    titulo = models.CharField(max_length=200)
    
    # Descripción simple (para notas rápidas del coach)
    descripcion_detallada = models.TextField(blank=True, null=True)
    
    # --- 🔥 ESTRUCTURA JSON PRO (La Clave de la Escalabilidad) ---
    # Al clonar la plantilla, copiamos su estructura aquí.
    # Esto permite editar el entrenamiento del alumno SIN afectar la plantilla original.
    # Y es lo que leerá la API de Garmin para subir el workout al reloj.
    estructura = models.JSONField(default=dict, blank=True)
    estructura_schema_version = models.CharField(max_length=10, default="1.0", help_text="Versión del schema JSON")

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
            
            self.porcentaje_cumplimiento = calcular_porcentaje_cumplimiento(self)
        
        return super().save(*args, **kwargs)

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
    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carreras_propias',
    )
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
        POLAR = "polar", "polar"
        WAHOO = "wahoo", "wahoo"
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
    entrenamiento = models.ForeignKey(
        "Entrenamiento",
        on_delete=models.SET_NULL,
        related_name="actividades_reconciliadas",
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
    # Raw audit/debug: string original de Strava (sport_type/type).
    # Ej: "Run", "TrailRun", "Ride", "VirtualRide" (se guarda tal cual llegue, pero normalizado a string).
    strava_sport_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    nombre = models.CharField(max_length=255)
    distancia = models.FloatField(help_text="Distancia en metros", default=0.0)
    tiempo_movimiento = models.IntegerField(help_text="Tiempo en segundos", default=0)
    fecha_inicio = models.DateTimeField()
    tipo_deporte = models.CharField(max_length=50)
    # `None` representa "dato faltante". NO usar 0 como faltante (kcal/elev/etc).
    desnivel_positivo = models.FloatField(null=True, blank=True)
    elev_gain_m = models.FloatField(default=0.0, help_text="Sumatoria de ascenso (metros).")
    elev_loss_m = models.FloatField(null=True, blank=True, help_text="Sumatoria de descenso (metros). NULL si faltante.")
    elev_total_m = models.FloatField(default=0.0, help_text="Elevación total (ascenso + descenso).")
    calories_kcal = models.FloatField(null=True, blank=True, help_text="Calorías (kcal). NULL si faltante.")
    effort = models.FloatField(
        null=True,
        blank=True,
        help_text="Esfuerzo (Strava relative_effort / suffer_score). NULL si faltante.",
    )
    canonical_load = models.FloatField(
        null=True,
        blank=True,
        help_text="Carga canónica (PR6) derivada de TSS/TRIMP/RPE/relative_effort.",
    )
    canonical_load_method = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Método usado para la carga canónica (tss_power/tss_gap/trimp/rpe/relative_effort).",
    )
    load_version = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Versión de la definición canónica de carga (ej: 1.0).",
    )
    ritmo_promedio = models.FloatField(blank=True, null=True, help_text="Metros por segundo")

    # Auditoría / visualización
    mapa_polilinea = models.TextField(blank=True, null=True)
    datos_brutos = models.JSONField(default=dict, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciliation_score = models.FloatField(default=0)
    reconciliation_method = models.CharField(max_length=40, blank=True, default="")

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


class AthleteSyncState(models.Model):
    """
    Estado simple (y observable) del sync/import por atleta.

    MVP:
    - Permite al frontend mostrar progreso (processed/target)
    - Permite auditoría: last_error, last_sync_at, último backfill count
    - Sirve como "coalescing" para recomputes de métricas (min fecha afectada)
    """

    class Status(models.TextChoices):
        IDLE = "IDLE", "IDLE"
        RUNNING = "RUNNING", "RUNNING"
        DONE = "DONE", "DONE"
        FAILED = "FAILED", "FAILED"

    alumno = models.OneToOneField(
        "Alumno",
        on_delete=models.CASCADE,
        related_name="sync_state",
        db_index=True,
    )
    provider = models.CharField(max_length=20, default="strava", db_index=True)

    sync_status = models.CharField(max_length=12, choices=Status.choices, default=Status.IDLE, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    # Progreso (ej: backfill de 200 actividades)
    target_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    last_backfill_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    # Coalescing para métricas: si varias actividades cambian, guardamos la mínima fecha afectada.
    metrics_pending_from = models.DateField(null=True, blank=True, db_index=True)
    metrics_status = models.CharField(max_length=12, choices=Status.choices, default=Status.IDLE, db_index=True)
    metrics_last_run_at = models.DateTimeField(null=True, blank=True)
    metrics_last_error = models.TextField(blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["provider", "sync_status"]),
            models.Index(fields=["provider", "metrics_status"]),
        ]


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
        # Evento válido pero sin identidad interna vinculada (se re-procesa al vincular).
        LINK_REQUIRED = "link_required", "link_required"
        DISCARDED = "discarded", "discarded"
        IGNORED = "ignored", "ignored"
        FAILED = "failed", "failed"

    class QuerySet(models.QuerySet):
        def failed(self):
            return self.filter(status=self.model.Status.FAILED)

        def stuck_processing(self, *, older_than_minutes: int | None = None):
            threshold = (
                int(older_than_minutes)
                if older_than_minutes is not None
                else int(getattr(settings, "STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES", 30))
            )
            cutoff = timezone.now() - timezone.timedelta(minutes=threshold)
            return self.filter(status=self.model.Status.PROCESSING, updated_at__lt=cutoff)

        def log_failed_threshold(self, *, logger: logging.Logger | None = None, threshold: int | None = None):
            threshold = (
                int(threshold)
                if threshold is not None
                else int(getattr(settings, "STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD", 50))
            )
            if threshold <= 0:
                return 0
            failed_count = self.failed().count()
            if failed_count >= threshold:
                from .utils.logging import safe_extra
                from .compliance import calcular_porcentaje_cumplimiento

                logger = logging.getLogger(__name__)
                logger.warning(
                    "strava.webhook.failed_threshold",
                    extra={"failed_count": failed_count, "threshold": threshold},
                )
            return failed_count

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
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

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
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["object_type", "aspect_type", "object_id"]),
            models.Index(fields=["provider", "provider_event_id"]),
        ]
        constraints = [
            # Requerimiento Fase 4: UniqueConstraint explícito para idempotencia y carreras.
            models.UniqueConstraint(fields=["provider", "event_uid"], name="uniq_strava_provider_event_uid"),
        ]

    objects = QuerySet.as_manager()

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
        DEFERRED = "deferred", "deferred"
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
        # Bloqueado por dependencia externa (ej: atleta todavía no vinculado).
        BLOCKED = "blocked", "blocked"
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


class ExternalIdentity(models.Model):
    """
    Identidad canónica externa (multi-provider), independiente de `Alumno`.

    - Permite recibir webhooks antes del onboarding: se crea UNLINKED.
    - Al vincularse (OAuth/admin), se enlaza a `Alumno` y se drenan eventos pendientes.
    - Shape SaaS: soporta multi-proveedor (Strava/Garmin/Coros/...) y multi-tenant por `Alumno`.
    """

    class Provider(models.TextChoices):
        STRAVA = "strava", "strava"
        SUUNTO = "suunto", "suunto"
        # Futuros providers:
        # GARMIN = "garmin", "garmin"
        # COROS = "coros", "coros"

    class Status(models.TextChoices):
        UNLINKED = "unlinked", "unlinked"
        LINKED = "linked", "linked"
        DISABLED = "disabled", "disabled"

    provider = models.CharField(max_length=20, choices=Provider.choices, db_index=True)
    # `owner_id` en Strava es numérico, pero lo persistimos como string para compat multi-proveedor.
    external_user_id = models.CharField(max_length=80, db_index=True)

    alumno = models.ForeignKey(
        "Alumno",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_identities",
        db_index=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNLINKED, db_index=True)
    linked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    profile = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_user_id"], name="uniq_external_identity_provider_user"),
            # Un Alumno no debe tener 2 identidades del mismo provider (cuando está linkeado).
            models.UniqueConstraint(
                fields=["provider", "alumno"],
                condition=Q(alumno__isnull=False),
                name="uniq_external_identity_provider_alumno_not_null",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),
            models.Index(fields=["provider", "status", "-updated_at"]),
        ]

    def __str__(self):
        if self.alumno_id:
            return f"{self.provider}:{self.external_user_id} -> alumno:{self.alumno_id}"
        return f"{self.provider}:{self.external_user_id} (unlinked)"

class OAuthCredential(models.Model):
    """
    Provider-agnostic OAuth token storage (PR10 foundation).

    Design:
      - One row per (alumno, provider) — enforced by UniqueConstraint.
      - Intended for future providers (Garmin, Coros, Suunto, Polar, Wahoo).
      - Strava continues using the allauth bridge (persist_oauth_tokens) unchanged.
      - Tokens NEVER logged. updated_at auto_now tracks token freshness.

    Multi-tenant discipline:
      Any query on this model must always filter by alumno (which is
      organisation-scoped via Alumno.entrenador). Never query globally.
    """

    alumno = models.ForeignKey(
        "Alumno",
        on_delete=models.CASCADE,
        related_name="oauth_credentials",
        db_index=True,
    )
    provider = models.CharField(max_length=40, db_index=True)
    external_user_id = models.CharField(max_length=120, db_index=True)
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "provider"],
                name="uniq_oauth_credential_alumno_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "alumno"]),
            models.Index(fields=["provider", "-updated_at"]),
        ]

    def __str__(self):
        # Safe: no token content exposed via string representation.
        return f"{self.provider}:alumno:{self.alumno_id}"


class CompletedActivity(models.Model):
    """
    Immutable ledger of real activities received from external providers.

    Design notes
    ------------
    - **Plan ≠ Real**: this model represents the *real* side only; planned
      workouts live in Entrenamiento.  Never couple these two directly here.
    - **Multi-tenant / fail-closed**: `organization` (coach user) is required
      (non-nullable) — a row without an owner must never exist.
    - **Idempotency**: the unique constraint on (organization, provider,
      provider_activity_id) prevents duplicate ingestion.
    - **Provider isolation**: raw_payload keeps the original vendor blob for
      re-processing; no provider-specific parsing happens in this model.
    """

    class Provider(models.TextChoices):
        STRAVA = "strava", "Strava"
        GARMIN = "garmin", "Garmin"
        COROS = "coros", "Coros"
        SUUNTO = "suunto", "Suunto"
        POLAR = "polar", "Polar"
        WAHOO = "wahoo", "Wahoo"
        MANUAL = "manual", "Manual"
        OTHER = "other", "Other"

    # ------------------------------------------------------------------
    # Tenant anchor (fail-closed: non-nullable)
    # ------------------------------------------------------------------
    organization = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="completed_activities",
        db_index=True,
        help_text="Coach / organisation that owns this activity record.",
    )

    # ------------------------------------------------------------------
    # Athlete
    # ------------------------------------------------------------------
    alumno = models.ForeignKey(
        "Alumno",
        on_delete=models.CASCADE,
        related_name="completed_activities",
        db_index=True,
        help_text="Athlete who performed the activity.",
    )

    # ------------------------------------------------------------------
    # Athlete bridge (PR-114: organization-first domain FK, nullable for
    # backward compatibility with rows ingested before PR-114).
    # Backfill of legacy rows is a separate, explicitly scoped task.
    # Both alumno and athlete coexist during the transition period.
    # ------------------------------------------------------------------
    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="completed_activities_v2",
        db_index=True,
        help_text=(
            "Organization-first Athlete FK. Nullable for backward compatibility "
            "with rows ingested before PR-114. Backfill is a separate task."
        ),
    )

    # ------------------------------------------------------------------
    # Activity data
    # ------------------------------------------------------------------
    sport = models.CharField(
        max_length=50,
        choices=TIPO_ACTIVIDAD,
        db_index=True,
        help_text="Normalised sport type (TIPO_ACTIVIDAD).",
    )
    start_time = models.DateTimeField(db_index=True)
    duration_s = models.IntegerField(help_text="Elapsed duration in seconds.")
    distance_m = models.FloatField(default=0.0, help_text="Distance in metres.")
    elevation_gain_m = models.FloatField(
        null=True, blank=True, help_text="Cumulative elevation gain in metres. NULL = data not available."
    )

    # ------------------------------------------------------------------
    # Provider provenance
    # ------------------------------------------------------------------
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        db_index=True,
    )
    provider_activity_id = models.CharField(
        max_length=120,
        db_index=True,
        help_text="Opaque ID assigned by the provider (e.g. Strava activity id).",
    )

    # ------------------------------------------------------------------
    # Raw audit payload (provider-specific; never parse here)
    # ------------------------------------------------------------------
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Original provider payload kept for auditing and future re-processing.",
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["organization", "-start_time"]),
            models.Index(fields=["alumno", "-start_time"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "provider", "provider_activity_id"],
                name="uniq_completed_activity_org_provider_id",
            ),
        ]
        verbose_name = "Completed Activity"
        verbose_name_plural = "Completed Activities"

    def __str__(self):
        return f"{self.sport} | {self.alumno_id} | {self.provider}:{self.provider_activity_id}"


@receiver(post_save, sender=Pago)
def actualizar_pago_alumno(sender, instance, **kwargs):
    if instance.es_valido:
        alumno = instance.alumno
        if not alumno.fecha_ultimo_pago or instance.fecha_pago > alumno.fecha_ultimo_pago:
            alumno.fecha_ultimo_pago = instance.fecha_pago
            alumno.save()


# ==============================================================================
#  DOMAIN FOUNDATION — P1 (organization-first architecture)
# ==============================================================================

class Organization(models.Model):
    """
    Tenant root for all Quantoryn domain entities.
    Every organization-scoped record must reference this model.

    Multi-tenant discipline: queries must always filter by organization.
    An organization without an active CoachSubscription is read-only.
    """
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "-created_at"]),
        ]

    def __str__(self):
        return self.name


class Team(models.Model):
    """
    A named subgroup within an Organization.
    Athletes are assigned to teams for training group segmentation.

    Tenancy: Team is scoped to Organization. Queries must filter by
    organization before filtering by team.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "name")
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.organization.name} / {self.name}"


class Membership(models.Model):
    """
    Access gate between a User and an Organization.

    Fail-closed: a user is authorized to access an organization's data only
    if they have an active Membership record with an appropriate role.
    Missing membership = deny, regardless of other user properties.

    Multi-tenant discipline:
    - All organization-scoped queries must validate membership first.
    - Never infer membership from request context — always resolve explicitly.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        COACH = "coach", "Coach"
        ATHLETE = "athlete", "Athlete"
        STAFF = "staff", "Staff"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    staff_title = models.CharField(
        max_length=60, blank=True, default="",
        help_text="e.g. physiotherapist, nutritionist, doctor, admin"
    )
    team = models.ForeignKey(
        "Team",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="memberships",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_membership_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "role", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.organization} [{self.role}]"


class Coach(models.Model):
    """
    Organization-scoped coach identity.

    A Coach is a User who holds a Membership.role = 'coach' or 'owner'
    within a specific Organization. This model makes that relationship
    explicit for use as a FK anchor in planning and assignment entities.

    A User may be a Coach in multiple Organizations.
    Each Coach record represents one (User, Organization) pairing.
    The UniqueConstraint enforces one active Coach record per (user, org) pair.

    Do NOT confuse with the legacy 'entrenador' User FK pattern on Alumno.
    entrenador = legacy pattern (User directly FK'd on Alumno, Spanish-named).
    Coach = new organization-first model (organization-scoped, English-named).
    Migration from entrenador → Coach is a separate, explicitly scoped PR.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coach_profiles",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="coaches",
        db_index=True,
    )
    bio = models.TextField(blank=True, default="")
    certifications = models.TextField(blank=True, default="")
    specialties = models.CharField(max_length=300, blank=True, default="")
    years_experience = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_coach_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return f"Coach:{self.user_id} @ {self.organization_id}"


class Athlete(models.Model):
    """
    Organization-scoped athlete identity.

    An Athlete is a User who holds a Membership.role = 'athlete'
    within a specific Organization. This model is the FK anchor for
    all athlete-specific domain entities: profile, goals, assignments,
    activities, and analytics.

    Organization scoping is non-nullable and fail-closed.
    A row without an organization must never exist.

    Do NOT confuse with the legacy 'Alumno' model.
    Alumno = legacy Spanish model (entrenador-scoped, per-coach, not per-org).
    Athlete = new organization-first model (organization-scoped, English-named).
    Migration from Alumno → Athlete is a separate, explicitly scoped PR.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="athlete_profiles",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athletes",
        db_index=True,
    )
    coach = models.ForeignKey(
        "Coach",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athletes",
        db_index=True,
        help_text=(
            "Primary coach for this athlete within this organization. "
            "Nullable: an athlete may exist before a coach is assigned. "
            "Full multi-coach assignment patterns are handled by PR-104 "
            "AthleteCoachAssignment."
        ),
    )
    team = models.ForeignKey(
        "Team",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athletes",
        db_index=True,
    )
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_athlete_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "team", "is_active"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return f"Athlete:{self.user_id} @ {self.organization_id}"


# ==============================================================================
# PR-143: AthleteZone — physiological threshold anchors per athlete
# ==============================================================================

class AthleteZone(models.Model):
    """
    Current physiological threshold anchors for an Athlete.

    Stores the three primary zone anchors used for TSS/IF calculations
    and intensity zone derivation:
    - ftp_watts: Functional Threshold Power (cycling/running power)
    - lthr_bpm: Lactate Threshold Heart Rate in beats per minute
    - threshold_pace_sec_per_km: Threshold running pace in seconds per km

    All fields are nullable: a zone record may exist without all anchors being set.
    Multi-tenant: organization is derived from athlete.organization — no direct FK needed.
    OneToOne: one active zone record per athlete. Update in place; do not append rows.
    """

    athlete = models.OneToOneField(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="zone",
    )
    ftp_watts = models.FloatField(
        null=True, blank=True,
        help_text="Functional Threshold Power in watts.",
    )
    lthr_bpm = models.FloatField(
        null=True, blank=True,
        help_text="Lactate Threshold Heart Rate in beats per minute.",
    )
    threshold_pace_sec_per_km = models.FloatField(
        null=True, blank=True,
        help_text="Threshold running pace in seconds per kilometre.",
    )
    recorded_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of last update.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["athlete"]),
        ]

    def __str__(self):
        return (
            f"AthleteZone Athlete:{self.athlete_id} "
            f"FTP={self.ftp_watts}W LTHR={self.lthr_bpm}bpm "
            f"Pace={self.threshold_pace_sec_per_km}s/km"
        )


class AthleteCoachAssignment(models.Model):
    """
    Explicit assignment of a Coach to an Athlete within an Organization.

    Role types:
    - primary: The lead coach. Only one primary assignment may be active
      per (athlete, organization) at any given time. Enforced by both
      a DB UniqueConstraint and the service layer.
    - assistant: Supporting coach. Multiple active assistants allowed.

    Active state: an assignment is active when ended_at is None.
    ended_at is set (never deleted) when the relationship ends, preserving
    the full coaching history.

    Tenancy: organization FK is non-nullable. athlete.organization and
    coach.organization must both equal this organization. Validated at
    the service layer in core/services_assignment.py.

    is_active property derives from ended_at to avoid dual-state
    inconsistency between a boolean flag and the ended_at timestamp.
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        ASSISTANT = "assistant", "Assistant"

    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="coach_assignments",
        db_index=True,
    )
    coach = models.ForeignKey(
        "Coach",
        on_delete=models.CASCADE,
        related_name="athlete_assignments",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_coach_assignments",
        db_index=True,
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="coach_assignments_made",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One active primary coach per (athlete, organization) at a time
            models.UniqueConstraint(
                fields=["athlete", "organization"],
                condition=Q(role="primary", ended_at__isnull=True),
                name="uniq_active_primary_coach_per_athlete_org",
            )
        ]
        indexes = [
            models.Index(fields=["athlete", "organization", "role"]),
            models.Index(fields=["coach", "organization"]),
            models.Index(fields=["organization", "role"]),
        ]

    @property
    def is_active(self) -> bool:
        """An assignment is active when ended_at is None."""
        return self.ended_at is None

    def __str__(self):
        status = "active" if self.ended_at is None else "ended"
        return (
            f"Athlete:{self.athlete_id} ← {self.role} Coach:{self.coach_id} "
            f"@ Org:{self.organization_id} [{status}]"
        )


class AthleteProfile(models.Model):
    """
    Physical and performance profile for an Athlete.

    Values feed analytics computation: training zones, TSS scaling,
    PMC modeling, and injury risk thresholds.

    One profile per athlete (OneToOneField). Updates are timestamped.
    All physiological fields are nullable — real athletes may not have
    all values measured at profile creation time.

    Zone fields (hr_zones_json, pace_zones_json, power_zones_json) store
    structured zone data as JSON. This supports both manual entry and
    future automatic recalculation from provider data or test results.

    Multi-tenant: organization comes through the athlete relation.
    The explicit organization FK is included for query efficiency on
    org-level analytics sweeps without joining through Athlete.

    Note: AthleteGoal is implemented in a separate PR once RaceEvent
    (PR-106) is available as a clean FK target.
    """

    class Discipline(models.TextChoices):
        RUN = "run", "Running"
        TRAIL = "trail", "Trail Running"
        BIKE = "bike", "Cycling"
        SWIM = "swim", "Swimming"
        TRIATHLON = "triathlon", "Triathlon"
        OTHER = "other", "Other"

    # ------------------------------------------------------------------
    # Identity anchors
    # ------------------------------------------------------------------
    athlete = models.OneToOneField(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="profile",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_profiles",
        db_index=True,
    )

    # ------------------------------------------------------------------
    # Demographics
    # ------------------------------------------------------------------
    birth_date = models.DateField(
        null=True, blank=True,
        help_text="Full birth date. Preferred over age field when available.",
    )
    age = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Age in years. Used when birth_date is unknown.",
    )
    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    bmi = models.FloatField(
        null=True, blank=True,
        help_text="Body Mass Index. May be manually entered or computed.",
    )

    # ------------------------------------------------------------------
    # Cardiovascular
    # ------------------------------------------------------------------
    resting_hr_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    max_hr_bpm = models.PositiveSmallIntegerField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------
    vo2max = models.FloatField(
        null=True, blank=True,
        help_text="VO2max in ml/kg/min (lab or estimated).",
    )
    ftp_watts = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Functional Threshold Power in watts (cycling).",
    )
    vam = models.FloatField(
        null=True, blank=True,
        help_text="Velocidad Ascensión Media in m/h (vertical climbing speed).",
    )
    lactate_threshold_pace_s_per_km = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Lactate threshold pace in seconds per km (running).",
    )
    running_economy = models.FloatField(
        null=True, blank=True,
        help_text="Running economy in ml O2/kg/km.",
    )
    training_age_years = models.PositiveSmallIntegerField(null=True, blank=True)
    dominant_discipline = models.CharField(
        max_length=20,
        choices=Discipline.choices,
        blank=True, default="",
    )

    # ------------------------------------------------------------------
    # Injury state
    # ------------------------------------------------------------------
    is_injured = models.BooleanField(
        default=False, db_index=True,
        help_text="Current injury flag. Affects training load recommendations.",
    )
    injury_notes = models.TextField(blank=True, default="")

    # ------------------------------------------------------------------
    # Training zones (JSON — supports manual entry and auto-recalculation)
    # ------------------------------------------------------------------
    hr_zones_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Heart rate zones as JSON. "
            "Structure: {z1: {min_bpm, max_bpm}, z2: ..., ...}. "
            "May be manually entered or auto-recalculated from max_hr_bpm."
        ),
    )
    pace_zones_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Running pace zones as JSON. "
            "Structure: {z1: {min_s_km, max_s_km}, ...}. "
            "May be manually entered or auto-recalculated from lactate_threshold."
        ),
    )
    power_zones_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Cycling power zones as JSON. "
            "Structure: {z1: {min_w, max_w}, ...}. "
            "May be manually entered or auto-recalculated from ftp_watts."
        ),
    )

    # ------------------------------------------------------------------
    # Freeform notes + audit
    # ------------------------------------------------------------------
    notes = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athlete_profile_updates",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.athlete_id is not None
            and self.organization_id is not None
            and self.athlete.organization_id != self.organization_id
        ):
            raise ValidationError(
                "AthleteProfile.organization must match athlete.organization. "
                "Cross-organization profiles are not permitted."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Profile: Athlete:{self.athlete_id} @ Org:{self.organization_id}"


# ==============================================================================
# PR-106: RaceEvent — organization-scoped competition catalog
# ==============================================================================

class RaceEvent(models.Model):
    """
    A target competition registered by an organization.

    Used as the anchor for AthleteGoal.target_event (PR-105/future) and
    training block periodization. Each organization maintains its own event
    catalog — two organizations may independently register the same race.

    Priority belongs in AthleteGoal (per athlete), not here.

    Multi-tenant: organization FK is non-nullable.
    All queries must filter by organization.
    """

    class Discipline(models.TextChoices):
        RUN = "run", "Running"
        TRAIL = "trail", "Trail Running"
        BIKE = "bike", "Cycling"
        SWIM = "swim", "Swimming"
        TRIATHLON = "triathlon", "Triathlon"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="race_events",
        db_index=True,
    )
    name = models.CharField(max_length=300)
    discipline = models.CharField(
        max_length=20,
        choices=Discipline.choices,
        db_index=True,
    )
    event_date = models.DateField(db_index=True)
    location = models.CharField(max_length=300, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    distance_km = models.FloatField(null=True, blank=True)
    elevation_gain_m = models.FloatField(
        null=True, blank=True,
        help_text="Total elevation gain in meters (relevant for trail/MTB events).",
    )
    event_url = models.URLField(
        blank=True, default="",
        help_text="Official event URL.",
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="race_events_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "event_date"],
                name="uniq_race_event_per_org_name_date",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "event_date"]),
            models.Index(fields=["organization", "discipline", "event_date"]),
        ]
        ordering = ["event_date"]

    def __str__(self):
        return f"{self.name} ({self.event_date}) [{self.organization_id}]"


# ==============================================================================
# PR-107: AthleteGoal — athlete objective model
# ==============================================================================

class AthleteGoal(models.Model):
    """
    A declared performance objective for an Athlete within an organization.

    Supports both race-linked goals (target_event set) and personal goals
    (target_event null, target_date used instead).

    Priority belongs here — the same RaceEvent may have different importance
    for different athletes. A coach may not want all athletes targeting the
    same race as their A priority.

    Invariants enforced at model level:
    - goal.organization must equal athlete.organization
    - if target_event is set: target_event.organization must equal goal.organization
    - at most one active goal per (athlete, priority)

    Multi-tenant: organization FK is non-nullable.
    """

    class Priority(models.TextChoices):
        A = "A", "A — Peak goal"
        B = "B", "B — Secondary goal"
        C = "C", "C — Developmental goal"

    class GoalType(models.TextChoices):
        FINISH = "finish", "Finish"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_goals",
        db_index=True,
    )
    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="goals",
        db_index=True,
    )
    target_event = models.ForeignKey(
        "RaceEvent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athlete_goals",
    )
    title = models.CharField(max_length=300)
    priority = models.CharField(
        max_length=5,
        choices=Priority.choices,
        db_index=True,
    )
    goal_type = models.CharField(
        max_length=20,
        choices=GoalType.choices,
        default=GoalType.FINISH,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )
    target_date = models.DateField(
        null=True, blank=True,
        help_text="Target date for personal goals not linked to a RaceEvent.",
        db_index=True,
    )
    coach_notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athlete_goals_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "priority"],
                condition=Q(status="active"),
                name="uniq_active_priority_per_athlete",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["athlete", "status", "priority"]),
        ]
        ordering = ["priority", "target_date"]

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}

        # Invariant 1: goal.organization must match athlete.organization
        if (
            self.athlete_id is not None
            and self.organization_id is not None
            and self.athlete.organization_id != self.organization_id
        ):
            errors["organization"] = (
                "AthleteGoal.organization must match athlete.organization. "
                "Cross-organization goals are not permitted."
            )

        # Invariant 2: if target_event is set, it must belong to the same org
        if (
            self.target_event_id is not None
            and self.organization_id is not None
            and self.target_event.organization_id != self.organization_id
        ):
            errors["target_event"] = (
                "target_event.organization must match goal.organization. "
                "Cross-organization event links are not permitted."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        event_part = f" → {self.target_event.name}" if self.target_event_id else ""
        return (
            f"[{self.priority}] {self.title}{event_part} "
            f"({self.status}) — Athlete:{self.athlete_id}"
        )


# ==============================================================================
# PR-111: WorkoutLibrary — organization-scoped workout template container
# ==============================================================================

class WorkoutLibrary(models.Model):
    """
    Named collection of workout templates for an Organization.

    The library is the container from which coaches select and assign
    workouts to athletes. Templates inside the library are PlannedWorkout
    records with is_template=True and a library FK pointing here (PR-112).

    Visibility:
    - is_public=True: all coaches in the organization can view and use
      templates from this library.
    - is_public=False: private library, visible only to created_by coach.

    Multi-tenant: organization FK is non-nullable. Cross-org access is denied.
    """

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_libraries",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_public = models.BooleanField(
        default=True,
        help_text="If True, all coaches in the organization can access this library.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="workout_libraries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "name")
        indexes = [
            models.Index(fields=["organization", "is_public"]),
        ]
        ordering = ["name"]

    def __str__(self):
        visibility = "public" if self.is_public else "private"
        return f"{self.name} ({visibility}) — Org:{self.organization_id}"


# ==============================================================================
# PR-112: PlannedWorkout + WorkoutBlock + WorkoutInterval
# Structured planning domain models — plan-side only, Plan ≠ Real.
# ==============================================================================

class PlannedWorkout(models.Model):
    """
    A reusable workout prescription stored inside a WorkoutLibrary.

    PLAN ≠ REAL INVARIANT:
    This model stores coaching intent only. It must never store execution
    outcomes (actual distance, actual duration, actual HR, actual power).
    CompletedActivity is the source of truth for what actually happened.
    PlanRealCompare (future PR) is the explicit reconciliation record.

    Modification audit:
    - structure_version increments when the prescription is materially changed.
    - Never reset to 1 after creation.

    Multi-tenant: organization FK is non-nullable. library.organization must
    equal organization (enforced in clean()).
    """

    class Discipline(models.TextChoices):
        RUN = "run", "Running"
        TRAIL = "trail", "Trail Running"
        BIKE = "bike", "Cycling"
        SWIM = "swim", "Swimming"
        STRENGTH = "strength", "Strength"
        MOBILITY = "mobility", "Mobility"
        TRIATHLON = "triathlon", "Triathlon"
        OTHER = "other", "Other"

    class SessionType(models.TextChoices):
        BASE = "base", "Base / Easy"
        THRESHOLD = "threshold", "Threshold"
        INTERVAL = "interval", "Interval"
        LONG = "long", "Long"
        RECOVERY = "recovery", "Recovery"
        RACE_SIMULATION = "race_simulation", "Race Simulation"
        STRENGTH = "strength", "Strength"
        MOBILITY = "mobility", "Mobility"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="planned_workouts",
        db_index=True,
    )
    library = models.ForeignKey(
        "WorkoutLibrary",
        on_delete=models.CASCADE,
        related_name="planned_workouts",
        db_index=True,
    )
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    discipline = models.CharField(
        max_length=20,
        choices=Discipline.choices,
        db_index=True,
    )
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.OTHER,
        db_index=True,
    )
    estimated_duration_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Coach-estimated total duration in seconds. Planning only.",
    )
    estimated_distance_meters = models.FloatField(
        null=True, blank=True,
        help_text="Coach-estimated total distance in meters. Planning only.",
    )
    structure_version = models.PositiveSmallIntegerField(
        default=1,
        help_text="Increments on material prescription changes. Never reset.",
    )

    # PR-118: dominant target variable for compliance scoring
    class PrimaryTarget(models.TextChoices):
        DURATION      = "duration",       "Duration"
        DISTANCE      = "distance",       "Distance"
        ELEVATION_GAIN = "elevation_gain", "Elevation Gain"
        PACE          = "pace",           "Pace"
        HR_ZONE       = "hr_zone",        "Heart Rate Zone (future)"

    primary_target_variable = models.CharField(
        max_length=20,
        choices=PrimaryTarget.choices,
        blank=True,
        default="",
        help_text=(
            "Dominant target variable for Plan vs Real compliance scoring. "
            "If blank, the reconciliation engine auto-selects based on available "
            "estimated targets. Options: duration, distance, elevation_gain, pace, hr_zone."
        ),
    )

    # PR-143: Advanced metrics — training load intent anchors
    planned_tss = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Planned Training Stress Score. "
            "Coach-estimated TSS for the session. Planning only — never derived from "
            "execution data (Plan ≠ Real invariant)."
        ),
    )
    planned_if = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Planned Intensity Factor (0.0–1.5+). "
            "Ratio of planned NP/AP to athlete FTP. Planning only."
        ),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="planned_workouts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "discipline", "session_type"]),
            models.Index(fields=["library"]),
        ]
        ordering = ["name"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.library_id is not None
            and self.organization_id is not None
            and self.library.organization_id != self.organization_id
        ):
            raise ValidationError(
                "PlannedWorkout.organization must match library.organization. "
                "Cross-organization workout prescriptions are not permitted."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.name} [{self.discipline}/{self.session_type}] "
            f"v{self.structure_version} — Org:{self.organization_id}"
        )


class WorkoutBlock(models.Model):
    """
    An ordered top-level section of a PlannedWorkout.

    Examples: Warm-up, Main Set, Cooldown, Drills, Strength, Custom.

    Blocks define the macro structure of the session. Each block has an
    order_index that determines its position within the workout. The
    optional video_url supports strength and drill coaching workflows
    where technique video context is valuable.

    Multi-tenant: organization FK is non-nullable. planned_workout.organization
    must equal organization (enforced in clean()).
    """

    class BlockType(models.TextChoices):
        WARMUP = "warmup", "Warm-Up"
        MAIN = "main", "Main Set"
        COOLDOWN = "cooldown", "Cool-Down"
        DRILL = "drill", "Drill"
        STRENGTH = "strength", "Strength"
        CUSTOM = "custom", "Custom"

    planned_workout = models.ForeignKey(
        "PlannedWorkout",
        on_delete=models.CASCADE,
        related_name="blocks",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_blocks",
        db_index=True,
    )
    order_index = models.PositiveSmallIntegerField(
        help_text="Position of this block within the workout. Must be unique per workout.",
    )
    block_type = models.CharField(
        max_length=20,
        choices=BlockType.choices,
        default=BlockType.CUSTOM,
        db_index=True,
    )
    name = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Optional label for display. Defaults to block_type if blank.",
    )
    description = models.TextField(blank=True, default="")
    video_url = models.URLField(
        blank=True, default="",
        help_text="Optional technique/demo video link for strength and drill blocks.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["planned_workout", "order_index"],
                name="uniq_block_order_per_workout",
            ),
        ]
        ordering = ["order_index"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.planned_workout_id is not None
            and self.organization_id is not None
            and self.planned_workout.organization_id != self.organization_id
        ):
            raise ValidationError(
                "WorkoutBlock.organization must match planned_workout.organization. "
                "Cross-organization blocks are not permitted."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.name or self.block_type
        return f"Block[{self.order_index}] {label} → Workout:{self.planned_workout_id}"


class WorkoutInterval(models.Model):
    """
    An ordered instruction or repetition step inside a WorkoutBlock.

    Examples:
    - 5 × 1000m @ threshold pace with 90s recovery
    - 20 min @ Z2 HR
    - 3 × 10 push-ups (STRENGTH block, video_url for form)

    Intensity is expressed via metric_type, which determines which target
    fields are meaningful. All target fields are nullable — not every
    interval type uses all of them.

    An interval may be duration-based, distance-based, or purely
    descriptive (FREE). Do not force a metric that is not specified.

    Multi-tenant: organization FK is non-nullable. block.organization
    must equal organization (enforced in clean()).
    """

    class MetricType(models.TextChoices):
        HR_ZONE = "hr_zone", "HR Zone"
        PACE = "pace", "Pace"
        POWER = "power", "Power"
        RPE = "rpe", "RPE"
        FREE = "free", "Free / Descriptive"

    block = models.ForeignKey(
        "WorkoutBlock",
        on_delete=models.CASCADE,
        related_name="intervals",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_intervals",
        db_index=True,
    )
    order_index = models.PositiveSmallIntegerField(
        help_text="Position of this interval within the block. Must be unique per block.",
    )
    repetitions = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this interval is repeated (e.g., 5 for '5 × 1000m').",
    )
    metric_type = models.CharField(
        max_length=20,
        choices=MetricType.choices,
        default=MetricType.FREE,
        db_index=True,
    )
    description = models.TextField(
        blank=True, default="",
        help_text="Human-readable instruction. Always useful; required for FREE type.",
    )

    # Duration / distance — either, both, or neither may be set
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Interval duration in seconds.",
    )
    distance_meters = models.FloatField(
        null=True, blank=True,
        help_text="Interval distance in meters.",
    )

    # Intensity target range — interpretation depends on metric_type
    target_value_low = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Lower bound of intensity target. "
            "HR zone number / pace s/km min / power watts min / RPE low."
        ),
    )
    target_value_high = models.FloatField(
        null=True, blank=True,
        help_text="Upper bound of intensity target.",
    )
    target_label = models.CharField(
        max_length=100, blank=True, default="",
        help_text='Human-readable intensity label, e.g. "Z2", "threshold", "10k pace".',
    )

    # Recovery
    recovery_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Rest/recovery duration after each repetition, in seconds.",
    )
    recovery_distance_meters = models.FloatField(
        null=True, blank=True,
        help_text="Recovery distance (e.g. walk 200m) after each repetition.",
    )

    # Optional video for strength/drill coaching context
    video_url = models.URLField(
        blank=True, default="",
        help_text="Optional demonstration video for strength or drill intervals.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["block", "order_index"],
                name="uniq_interval_order_per_block",
            ),
        ]
        ordering = ["order_index"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if (
            self.block_id is not None
            and self.organization_id is not None
            and self.block.organization_id != self.organization_id
        ):
            raise ValidationError(
                "WorkoutInterval.organization must match block.organization. "
                "Cross-organization intervals are not permitted."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        metric = self.metric_type
        label = self.target_label or metric
        duration = f"{self.duration_seconds}s" if self.duration_seconds else ""
        distance = f"{self.distance_meters}m" if self.distance_meters else ""
        extent = duration or distance or "open"
        return (
            f"Interval[{self.order_index}] {label} × {extent} "
            f"→ Block:{self.block_id}"
        )


class WorkoutAssignment(models.Model):
    """
    Assigns a PlannedWorkout to a specific Athlete on a specific date.

    PLAN ≠ REAL INVARIANT:
    This model records delivery, scheduling, and assignment-level
    personalization only. It does NOT store execution outcomes (actual
    distance, actual HR, actual power). Completion is recorded on
    CompletedActivity. The link between assignment and completion is
    established by PlanRealCompare (future PR-118).

    Personalization without template mutation:
    Assignment-level override fields (target_zone_override,
    target_pace_override, target_rpe_override, target_power_override)
    allow per-athlete personalization. The shared PlannedWorkout template
    is NEVER modified by an assignment operation. Coaches can reuse one
    template for many athletes and personalize each assignment independently.

    Multiple sessions per day:
    day_order supports ordered same-day training. The unique constraint
    on (athlete, scheduled_date, day_order) prevents collisions while
    allowing up to N sessions on the same date.

    Day-swap:
    athlete_moved_date records if the athlete rescheduled the session.
    scheduled_date is NEVER modified after creation.

    Multi-tenant: organization FK non-nullable. Both athlete and
    planned_workout must belong to the same organization (enforced in clean()).
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        MOVED = "moved", "Moved"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"
        CANCELED = "canceled", "Canceled"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_assignments",
        db_index=True,
    )
    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="workout_assignments",
        db_index=True,
    )
    planned_workout = models.ForeignKey(
        "PlannedWorkout",
        on_delete=models.CASCADE,
        related_name="assignments",
        db_index=True,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="workout_assignments_made",
    )

    # Scheduling
    scheduled_date = models.DateField(
        db_index=True,
        help_text="Original assignment date. Never modified after creation.",
    )
    athlete_moved_date = models.DateField(
        null=True, blank=True, db_index=True,
        help_text=(
            "If the athlete rescheduled, this records the new execution date. "
            "scheduled_date is never changed."
        ),
    )
    day_order = models.PositiveSmallIntegerField(
        default=1,
        help_text="Order of this session within the day (1=first, 2=second, etc.).",
    )

    # Lifecycle
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
    )

    # Assignment-level notes (visible to both coach and athlete)
    coach_notes = models.TextField(
        blank=True, default="",
        help_text="Coach instructions specific to this assignment. Not stored on template.",
    )
    athlete_notes = models.TextField(
        blank=True, default="",
        help_text="Athlete feedback/notes. Written only by the athlete.",
    )

    # Assignment-level personalization overrides
    # These allow per-athlete target adjustment without mutating the shared template.
    target_zone_override = models.CharField(
        max_length=100, blank=True, default="",
        help_text='e.g. "Z3" — overrides library template zone for this athlete.',
    )
    target_pace_override = models.CharField(
        max_length=100, blank=True, default="",
        help_text='e.g. "4:30/km" — overrides library template pace for this athlete.',
    )
    target_rpe_override = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="RPE 1–10 override for this assignment. Null = use template default.",
    )
    target_power_override = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Power target in watts override. Null = use template default.",
    )

    # Snapshot versioning
    snapshot_version = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Records the PlannedWorkout.structure_version at assignment time. "
            "Coaches can detect if the underlying template was updated after assignment."
        ),
    )

    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "scheduled_date", "day_order"],
                name="uniq_assignment_athlete_date_order",
            )
        ]
        indexes = [
            models.Index(fields=["athlete", "scheduled_date", "status"]),
            models.Index(fields=["organization", "scheduled_date"]),
            models.Index(fields=["planned_workout"]),
        ]
        ordering = ["scheduled_date", "day_order"]

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if (
            self.athlete_id is not None
            and self.organization_id is not None
            and self.athlete.organization_id != self.organization_id
        ):
            errors["athlete"] = (
                "WorkoutAssignment.athlete must belong to the same organization. "
                "Cross-organization assignments are not permitted."
            )
        if (
            self.planned_workout_id is not None
            and self.organization_id is not None
            and self.planned_workout.organization_id != self.organization_id
        ):
            errors["planned_workout"] = (
                "WorkoutAssignment.planned_workout must belong to the same organization. "
                "Cross-organization assignments are not permitted."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def effective_date(self):
        """Returns athlete_moved_date if set, otherwise scheduled_date."""
        return self.athlete_moved_date or self.scheduled_date

    def __str__(self):
        return (
            f"Assignment: Athlete:{self.athlete_id} ← "
            f"Workout:{self.planned_workout_id} on {self.effective_date} "
            f"#{self.day_order} [{self.status}]"
        )


class WorkoutDeliveryRecord(models.Model):
    """
    Tracks the outbound delivery of a WorkoutAssignment to a provider device.

    One record per (assignment, provider) — enforced by UniqueConstraint.
    This is the idempotency anchor for the suunto.push_guide Celery task.

    PLAN ≠ REAL: This model lives on the planning/delivery side.
    It records push attempts only — never execution outcomes.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_delivery_records",
        db_index=True,
    )
    assignment = models.ForeignKey(
        "WorkoutAssignment",
        on_delete=models.CASCADE,
        related_name="delivery_records",
        db_index=True,
    )
    provider = models.CharField(max_length=40, db_index=True)
    external_guide_id = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    snapshot_version = models.PositiveSmallIntegerField(
        default=1,
        help_text="PlannedWorkout.structure_version captured at push time.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "provider"],
                name="uniq_delivery_record_assignment_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "provider", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"DeliveryRecord({self.pk}) {self.provider} "
            f"assignment={self.assignment_id} status={self.status}"
        )


class ActivityStream(models.Model):
    """
    Lightweight event/metadata stream attached to a CompletedActivity.

    PLAN ≠ REAL: This model lives exclusively on the execution side.
    It records ingestion events, normalization steps, and metric
    snapshots for a CompletedActivity. It must never reference planning
    models (PlannedWorkout, WorkoutAssignment) or store intent.

    Design: event-stream, not physiological time-series.
    Each record is an event in the activity's processing lifecycle.
    Multiple records of the same stream_type are allowed (e.g., two
    INGEST events for the same activity are valid — re-ingestion).
    This is intentional: do not add a unique constraint on stream_type
    alone, as that would prevent re-ingestion and event replay.

    Provider boundary: `provider` is a CharField (string slug).
    It must never be a FK to a provider registry. This keeps
    the execution domain decoupled from the integration layer.

    Multi-tenant: scoped through completed_activity.organization.
    Always query via activity__organization — no direct org FK needed.
    """

    class StreamType(models.TextChoices):
        INGEST = "ingest", "Ingest"
        NORMALIZED = "normalized", "Normalized"
        PROVIDER_UPDATE = "provider_update", "Provider Update"
        METRIC_SNAPSHOT = "metric_snapshot", "Metric Snapshot"
        CUSTOM = "custom", "Custom"

    completed_activity = models.ForeignKey(
        "CompletedActivity",
        on_delete=models.CASCADE,
        related_name="activity_streams",
        db_index=True,
    )
    stream_type = models.CharField(
        max_length=20,
        choices=StreamType.choices,
        db_index=True,
    )
    provider = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Provider slug (e.g. 'strava'). String, never a FK.",
    )
    payload = models.JSONField(
        help_text="Event payload. Structure is stream_type-dependent.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["completed_activity", "stream_type"]),
            models.Index(fields=["completed_activity", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"ActivityStream:{self.stream_type} "
            f"→ Activity:{self.completed_activity_id} "
            f"[{self.provider or 'no-provider'}]"
        )


# ==============================================================================
#  PR-118: Plan vs Real Reconciliation — WorkoutReconciliation
# ==============================================================================

class WorkoutReconciliation(models.Model):
    """
    PR-118: Explicit Plan vs Real reconciliation record.

    PLAN ≠ REAL INVARIANT:
    This model bridges WorkoutAssignment (planning side) and CompletedActivity
    (execution side) without merging them. Neither the assignment nor the
    activity is ever modified by a reconciliation operation.

    One record per assignment (OneToOneField on assignment).
    The completed_activity FK is nullable: null means the assignment was
    missed, unmatched, ambiguous, or is still pending.

    State machine:
        pending    → initial state; auto-matching not yet attempted
        reconciled → assignment matched to an activity; compliance score computed
        unmatched  → auto-matching found no candidate in the time window
        missed     → effective_date has passed; no activity ever recorded
        ambiguous  → multiple candidates found; fail-closed (score = None)
        error      → matching or scoring raised an unexpected exception

    Compliance score (0..120):
        100 = planned target exactly met
        <100 = under-compliance
        >100 = over-compliance (athlete exceeded plan, hard cap at 120)
        0   = no execution data available

    Compliance categories (derived from score):
        not_completed  0–59
        regular        60–84
        completed      85–100
        over_completed 101–120

    Signals: structured strings (ComplianceSignal constants in
    services_reconciliation.py) stored as a JSON list for structured
    analysis and future alert wiring.

    Tenancy: organization FK is non-nullable, always derived from
    assignment.organization. Never accepted from client input.

    Interval-readiness: score_detail stores per-variable breakdown as JSON,
    allowing future sub-session or block-level detail to be appended without
    schema changes.
    """

    class State(models.TextChoices):
        PENDING    = "pending",    "Pending"
        RECONCILED = "reconciled", "Reconciled"
        UNMATCHED  = "unmatched",  "Unmatched"
        MISSED     = "missed",     "Missed"
        AMBIGUOUS  = "ambiguous",  "Ambiguous (Multiple Candidates)"
        ERROR      = "error",      "Error"

    class MatchMethod(models.TextChoices):
        AUTO   = "auto",   "Automatic"
        MANUAL = "manual", "Manual (Coach Override)"
        NONE   = "none",   "Not Matched"

    # ------------------------------------------------------------------
    # Tenant anchor — always derived from assignment, never client-set
    # ------------------------------------------------------------------
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_reconciliations",
        db_index=True,
        help_text="Tenant root. Always derived from assignment.organization.",
    )

    # ------------------------------------------------------------------
    # Planning side (non-nullable: each reconciliation record belongs to
    # exactly one assignment)
    # ------------------------------------------------------------------
    assignment = models.OneToOneField(
        "WorkoutAssignment",
        on_delete=models.CASCADE,
        related_name="reconciliation",
        help_text="The planned assignment being evaluated.",
    )

    # ------------------------------------------------------------------
    # Execution side (nullable: null when missed / unmatched / pending)
    # ------------------------------------------------------------------
    completed_activity = models.ForeignKey(
        "CompletedActivity",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="reconciliations",
        help_text=(
            "The matched real activity. Null when state is "
            "missed, unmatched, pending, ambiguous, or error."
        ),
    )

    # ------------------------------------------------------------------
    # Reconciliation state
    # ------------------------------------------------------------------
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.PENDING,
        db_index=True,
    )

    # ------------------------------------------------------------------
    # Matching metadata
    # ------------------------------------------------------------------
    match_method = models.CharField(
        max_length=10,
        choices=MatchMethod.choices,
        default=MatchMethod.NONE,
        help_text="How the activity was matched to the assignment.",
    )
    match_confidence = models.FloatField(
        null=True, blank=True,
        help_text="0..1. Confidence score from automatic matching.",
    )

    # ------------------------------------------------------------------
    # Compliance output
    # ------------------------------------------------------------------
    compliance_score = models.SmallIntegerField(
        null=True, blank=True,
        help_text="0..120. Null when no activity was matched.",
    )
    compliance_category = models.CharField(
        max_length=20, blank=True, default="",
        help_text="not_completed / regular / completed / over_completed.",
    )
    primary_target_used = models.CharField(
        max_length=20, blank=True, default="",
        help_text=(
            "Variable that drove the compliance score "
            "(duration / distance / pace / elevation_gain / hr_zone)."
        ),
    )

    # ------------------------------------------------------------------
    # Structured compliance detail + signals
    # Schema: {variable: {planned, actual, ratio, score, signals: []}}
    # Interval-ready: future block-level detail can be appended as
    # {"blocks": [...]} without schema migration.
    # ------------------------------------------------------------------
    score_detail = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Per-variable compliance breakdown. "
            "Schema: {variable: {planned, actual, ratio, score, signals}}. "
            "Populated when state=reconciled."
        ),
    )
    signals = models.JSONField(
        default=list, blank=True,
        help_text=(
            "Structured reconciliation signals (ComplianceSignal constants). "
            "Examples: under_completed, duration_short, possible_overreaching."
        ),
    )

    # ------------------------------------------------------------------
    # Audit + extensibility
    # ------------------------------------------------------------------
    reconciled_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when reconciliation score was last computed.",
    )
    notes = models.TextField(
        blank=True, default="",
        help_text=(
            "System diagnostic or coach notes. Extension point for future "
            "manual override workflow."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "state"]),
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["assignment"]),
            models.Index(fields=["completed_activity"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Workout Reconciliation"
        verbose_name_plural = "Workout Reconciliations"

    def __str__(self):
        return (
            f"Reconciliation: Assignment:{self.assignment_id} "
            f"[{self.state}] score={self.compliance_score}"
        )
