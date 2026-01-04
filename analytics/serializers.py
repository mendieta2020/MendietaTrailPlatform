from rest_framework import serializers

from analytics.models import (
    AlertaRendimiento,
    HistorialFitness,
    InjuryRiskSnapshot,
)

class _WeekRangeSerializer(serializers.Serializer):
    start = serializers.CharField()
    end = serializers.CharField()


class WeeklyActivityStatSerializer(serializers.Serializer):
    """
    Contrato explícito para stats_semanales (vista semanal).
    Asegura que calories_kcal esté presente en el JSON.
    """

    week = serializers.CharField()
    range = _WeekRangeSerializer()
    km = serializers.FloatField()
    elev_gain_m = serializers.IntegerField()
    calories_kcal = serializers.IntegerField()
    # Opcional: si el backend lo agrega en el futuro
    time_min = serializers.IntegerField(required=False, default=0)


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


class InjuryRiskSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = InjuryRiskSnapshot
        fields = [
            "fecha",
            "risk_level",
            "risk_score",
            "risk_reasons",
        ]


class AlertaRendimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertaRendimiento
        fields = [
            "id",
            "fecha",
            "alumno",
            "tipo",
            "mensaje",
            "valor_anterior",
            "valor_detectado",
            "visto_por_coach",
        ]