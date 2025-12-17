from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AlertaRendimientoViewSet, PMCDataView

router = DefaultRouter()
router.register(r"alerts", AlertaRendimientoViewSet, basename="analytics-alerts")

urlpatterns = [
    # Esta es la ruta que llama tu Dashboard: /api/analytics/pmc/
    path('pmc/', PMCDataView.as_view(), name='pmc_data'),
]

urlpatterns += router.urls