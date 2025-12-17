from django.db import models
from django.conf import settings
from django.db.models import Q

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
class AlertaRendimiento(models.Model):
    """
    Guarda eventos donde el atleta superó sus métricas teóricas.
    Ej: Hizo 20 min a 300w pero su FTP es 250w.
    """
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    fecha = models.DateField(auto_now_add=True)
    tipo = models.CharField(max_length=50, choices=[('FTP_UP', '📈 Posible Aumento de FTP'), ('HR_MAX', '❤️ Nueva FC Máxima')])
    valor_detectado = models.FloatField()
    valor_anterior = models.FloatField()
    mensaje = models.TextField()
    visto_por_coach = models.BooleanField(default=False)

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
        OVERTRAINING_RISK = "overtraining_risk", "overtraining_risk"
        LOW_COMPLIANCE = "low_compliance", "low_compliance"
        ANOMALY = "anomaly", "anomaly"

    class Severity(models.TextChoices):
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
    payload_json = models.JSONField(default=dict, blank=True)

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