from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlumnoViewSet, EntrenamientoViewSet, dashboard_entrenador

# --- IMPORTACIÓN NUEVA: CONEXIÓN CON ANALYTICS ---
# Importamos la vista que entrega los datos matemáticos (CTL, ATL, TSB)
# Esto es vital para que el futuro Dashboard pueda graficar la evolución.
from analytics.views import HistorialFitnessViewSet 

# Creamos el router principal
router = DefaultRouter()

# 1. Rutas del Core (Gestión Diaria)
router.register(r'alumnos', AlumnoViewSet)
router.register(r'entrenamientos', EntrenamientoViewSet)

# 2. Rutas de Ciencia de Datos (NUEVO)
# Esta ruta 'api/analytics/fitness/' expondrá el historial fisiológico
# para que el Frontend pueda pintar el gráfico de rendimiento.
router.register(r'analytics/fitness', HistorialFitnessViewSet, basename='fitness-history')

urlpatterns = [
    # API REST (JSON puro para la App/Frontend)
    path('api/', include(router.urls)),

    # Dashboard Visual (Renderizado por Django - "Cara Bonita" actual)
    # Nota: Asegúrate de que el nombre coincida con el redirect en views.py
    path('dashboard/', dashboard_entrenador, name='dashboard_entrenador'), 
]