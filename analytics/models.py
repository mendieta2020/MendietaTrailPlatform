from django.db import models
from core.models import Alumno

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