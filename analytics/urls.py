from django.urls import path
from .views import PMCDataView

urlpatterns = [
    # Esta es la ruta que llama tu Dashboard: /api/analytics/pmc/
    path('pmc/', PMCDataView.as_view(), name='pmc_data'),
]