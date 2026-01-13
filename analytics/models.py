from django.db import models
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import Alumno, Equipo, Entrenamiento, Actividad

class HistorialFitness(models.Model):
    """
    Guarda la evolución diaria del estado de forma del atleta.
    Basado en el modelo de Banister (Coggan):
    - CTL (Chronic Training Load): Fitness (42 días)
    - ATL (Acute Training Load): Fatiga (7 días)
    - TSB (Training Stress Balance): Forma (CTL - ATL)
    """
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='historial_fitness')
    fecha = models.DateField(db_index=True)
    
    # Métricas del día
    tss_diario = models.FloatField(default=0, help_text="Suma de TSS de todos los entrenamientos del día")
    
    # Métricas Acumuladas (Estado de Forma)
    ctl = models.FloatField(default=0, help_text="Fitness (Carga Crónica)")
    atl = models.FloatField(default=0, help_text="Fatiga (Carga Aguda)")
    tsb = models.FloatField(default=0, help_text="Forma (Equilibrio)")
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('alumno', 'fecha') # Un solo registro por día por alumno
        ordering = ['-fecha']
        verbose_name = "📈 Historial de Fitness"
        verbose_name_plural = "📈 Historial de Fitness"

    def __str__(self):
        return f"{self.fecha} - {self.alumno} (Forma: {self.tsb:.1f})"


class DailyActivityAgg(models.Model):
    """
    Agregación diaria por atleta y tipo (derivada de `core.Actividad`).

    - Idempotente: unique (alumno, fecha, sport)
    - Fuente para métricas (PMC) y summaries rápidos.
    """

    class Sport(models.TextChoices):
        RUN = "RUN", "RUN"
        TRAIL = "TRAIL", "TRAIL"
        BIKE = "BIKE", "BIKE"
        WALK = "WALK", "WALK"
        OTHER = "OTHER", "OTHER"

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="daily_activity_aggs", db_index=True)
    fecha = models.DateField(db_index=True)
    sport = models.CharField(max_length=10, choices=Sport.choices, db_index=True)

    # Sumas del día (MVP)
    load = models.FloatField(default=0, help_text="Carga/Esfuerzo del día (TSS/Relative Effort proxy)")
    distance_m = models.FloatField(default=0)
    elev_gain_m = models.FloatField(default=0)
    elev_loss_m = models.FloatField(default=0)
    elev_total_m = models.FloatField(default=0)
    duration_s = models.PositiveIntegerField(default=0)
    calories_kcal = models.FloatField(default=0, help_text="Calorías totales del día (kcal). Nunca NULL.")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("alumno", "fecha", "sport")
        indexes = [
            models.Index(fields=["alumno", "sport", "-fecha"]),
        ]
        ordering = ["-fecha"]


class PMCHistory(models.Model):
    """
    Serie diaria PMC (Banister/Coggan) calculada desde `DailyActivityAgg`.
    Soporta filtros por deporte agregados:
    - ALL: RUN+TRAIL+BIKE
    - RUN: RUN+TRAIL
    - BIKE: BIKE
    """

    class Sport(models.TextChoices):
        ALL = "ALL", "ALL"
        RUN = "RUN", "RUN"
        BIKE = "BIKE", "BIKE"

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="pmc_history", db_index=True)
    fecha = models.DateField(db_index=True)
    sport = models.CharField(max_length=10, choices=Sport.choices, db_index=True)

    tss_diario = models.FloatField(default=0)
    ctl = models.FloatField(default=0)
    atl = models.FloatField(default=0)
    tsb = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("alumno", "fecha", "sport")
        indexes = [
            models.Index(fields=["alumno", "sport", "-fecha"]),
        ]
        ordering = ["-fecha"]


class AnalyticsRangeCache(models.Model):
    """
    Cache persistente por atleta + rango.
    Usado para PMC y resúmenes semanales (evita recomputes costosos).
    """

    class CacheType(models.TextChoices):
        PMC = "PMC", "PMC"
        WEEK_SUMMARY = "WEEK_SUMMARY", "WEEK_SUMMARY"

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="analytics_cache", db_index=True)
    cache_type = models.CharField(max_length=30, choices=CacheType.choices, db_index=True)
    sport = models.CharField(max_length=10, default="ALL", db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    payload = models.JSONField(default=dict)
    last_computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("alumno", "cache_type", "sport", "start_date", "end_date")
        indexes = [
            models.Index(fields=["alumno", "cache_type", "sport", "start_date", "end_date"]),
        ]
        ordering = ["-last_computed_at"]


class AlertaRendimiento(models.Model):
    """
    Guarda eventos donde el atleta superó sus métricas teóricas.
    Ej: Hizo 20 min a 300w pero su FTP es 250w.
    """
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    fecha = models.DateField(auto_now_add=True, db_index=True)
    tipo = models.CharField(max_length=50, choices=[('FTP_UP', '📈 Posible Aumento de FTP'), ('HR_MAX', '❤️ Nueva FC Máxima')])
    valor_detectado = models.FloatField()
    valor_anterior = models.FloatField()
    mensaje = models.TextField()
    visto_por_coach = models.BooleanField(default=False)

    class Meta:
        indexes = [
            # Listado del coach por atleta + orden estable para paginación
            models.Index(fields=["alumno", "-fecha", "-id"]),
        ]
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.alumno} - {self.tipo}"


class InjuryRiskSnapshot(models.Model):
    """
    Snapshot diario del riesgo de lesión por atleta (v1).

    Multi-tenant: el "tenant" actual del sistema es el entrenador (User).
    Guardamos entrenador explícitamente para scoping rápido y robusto.
    """

    class RiskLevel(models.TextChoices):
        LOW = "LOW", "LOW"
        MEDIUM = "MEDIUM", "MEDIUM"
        HIGH = "HIGH", "HIGH"

    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="injury_risk_snapshots",
        db_index=True,
    )
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="injury_risk_snapshots",
        db_index=True,
    )
    fecha = models.DateField(db_index=True)

    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    risk_score = models.PositiveSmallIntegerField(default=0, help_text="0–100")
    risk_reasons = models.JSONField(default=list, blank=True, help_text="Lista de strings explicables")

    # Inputs del día (útiles para auditoría/QA)
    ctl = models.FloatField(default=0)
    atl = models.FloatField(default=0)
    tsb = models.FloatField(default=0)

    version = models.CharField(max_length=10, default="v1")
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("alumno", "fecha")
        indexes = [
            models.Index(fields=["entrenador", "fecha"]),
            models.Index(fields=["alumno", "-fecha"]),
        ]
        ordering = ["-fecha"]
        verbose_name = "🩺 Injury Risk Snapshot"
        verbose_name_plural = "🩺 Injury Risk Snapshots"

    def __str__(self):
        return f"{self.fecha} - {self.alumno} ({self.risk_level} {self.risk_score})"


class SessionComparison(models.Model):
    """
    Resultado persistido de "Plan vs Actual" por actividad importada.

    Multi-tenant: guardamos `entrenador` (tenant) explícito para scoping rápido.
    """

    class Classification(models.TextChoices):
        ON_TRACK = "on_track", "on_track"
        UNDER = "under", "under"
        OVER = "over", "over"
        ANOMALY = "anomaly", "anomaly"

    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_comparisons",
        db_index=True,
    )
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="session_comparisons",
        db_index=True,
    )
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="session_comparisons",
        db_index=True,
    )
    fecha = models.DateField(db_index=True)

    planned_session = models.ForeignKey(
        Entrenamiento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparisons",
    )
    activity = models.OneToOneField(
        Actividad,
        on_delete=models.CASCADE,
        related_name="comparison",
    )

    metrics_json = models.JSONField(default=dict, blank=True)
    compliance_score = models.PositiveSmallIntegerField(default=0, help_text="0–100")
    classification = models.CharField(max_length=20, choices=Classification.choices, db_index=True)
    explanation = models.TextField(blank=True, default="")
    next_action = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["entrenador", "-fecha"]),
            models.Index(fields=["alumno", "-fecha"]),
            models.Index(fields=["classification", "-created_at"]),
        ]


class Alert(models.Model):
    """
    Alertas automáticas (MVP robusto) para coach + UI futura.
    """

    class Type(models.TextChoices):
        # Coach Decision Layer v1 (accionables)
        INJURY_RISK_UP_AND_FATIGUE_HIGH = "injury_risk_up_and_fatigue_high", "injury_risk_up_and_fatigue_high"
        COMPLIANCE_DROP_WEEK = "compliance_drop_week", "compliance_drop_week"
        ACUTE_LOAD_SPIKE = "acute_load_spike", "acute_load_spike"
        FORM_TOO_NEGATIVE_SUSTAINED = "form_too_negative_sustained", "form_too_negative_sustained"
        MISSED_SESSIONS_VS_PLAN = "missed_sessions_vs_plan", "missed_sessions_vs_plan"

        # Legacy/MVP (se mantienen por compat)
        OVERTRAINING_RISK = "overtraining_risk", "overtraining_risk"
        LOW_COMPLIANCE = "low_compliance", "low_compliance"
        ANOMALY = "anomaly", "anomaly"

    class Severity(models.TextChoices):
        # v1 contract (coach-first)
        INFO = "info", "info"
        WARN = "warn", "warn"
        CRITICAL = "critical", "critical"
        # Legacy
        LOW = "LOW", "LOW"
        MEDIUM = "MEDIUM", "MEDIUM"
        HIGH = "HIGH", "HIGH"

    class Status(models.TextChoices):
        OPEN = "open", "open"
        CLOSED = "closed", "closed"

    entrenador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alerts",
        db_index=True,
    )
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        db_index=True,
    )
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="alerts",
        db_index=True,
    )

    type = models.CharField(max_length=40, choices=Type.choices, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.LOW, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)

    message = models.TextField()
    recommended_action = models.TextField(blank=True, default="")
    evidence_json = models.JSONField(default=dict, blank=True)
    visto_por_coach = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entrenador", "status", "-created_at"]),
            models.Index(fields=["alumno", "status", "-created_at"]),
            models.Index(fields=["type", "status", "-created_at"]),
        ]
        constraints = [
            # Evita spam: una alerta OPEN por (alumno,type)
            models.UniqueConstraint(
                fields=["alumno", "type"],
                condition=Q(status="open"),
                name="uniq_open_alert_per_type_alumno",
            )
        ]
