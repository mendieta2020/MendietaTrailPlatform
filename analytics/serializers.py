from rest_framework import serializers
from analytics.models import HistorialFitness  # Importación absoluta (más segura)

class HistorialFitnessSerializer(serializers.ModelSerializer):
    """
    Serializer optimizado para gráficos de rendimiento (PMC).
    Entrega solo los datos numéricos necesarios para reducir el payload JSON.
    """
    class Meta:
        model = HistorialFitness
        fields = [
            'fecha',       # Eje X
            'ctl',         # Fitness (Línea Azul)
            'atl',         # Fatiga (Línea Rosa)
            'tsb',         # Forma (Línea Amarilla)
            'tss_diario'   # Barras de carga (Opcional para gráficos mixtos)
        ]