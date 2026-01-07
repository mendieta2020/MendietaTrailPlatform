import django_filters

from core.models import Actividad


class ActividadFilter(django_filters.FilterSet):
    athlete_id = django_filters.NumberFilter(field_name="alumno_id")
    user_id = django_filters.NumberFilter(field_name="usuario_id")
    sport_type = django_filters.CharFilter(field_name="tipo_deporte", lookup_expr="iexact")
    strava_sport_type = django_filters.CharFilter(field_name="strava_sport_type", lookup_expr="iexact")
    start_date = django_filters.DateFilter(field_name="fecha_inicio", lookup_expr="date__gte")
    end_date = django_filters.DateFilter(field_name="fecha_inicio", lookup_expr="date__lte")
    validity = django_filters.ChoiceFilter(field_name="validity", choices=Actividad.Validity.choices)
    source = django_filters.ChoiceFilter(field_name="source", choices=Actividad.Source.choices)
    has_training = django_filters.BooleanFilter(method="filter_has_training")

    class Meta:
        model = Actividad
        fields = []

    def filter_has_training(self, queryset, name, value):
        if value is True:
            return queryset.filter(entrenamiento__isnull=False)
        if value is False:
            return queryset.filter(entrenamiento__isnull=True)
        return queryset
