# core/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlumnoViewSet, EntrenamientoViewSet, dashboard_entrenador

# Creamos un router para las ViewSets (API REST estándar)
router = DefaultRouter()
router.register(r'alumnos', AlumnoViewSet, basename='alumno')
router.register(r'entrenamientos', EntrenamientoViewSet, basename='entrenamiento')

urlpatterns = [
    # Rutas automáticas de la API (GET, POST, PUT, DELETE)
    path('', include(router.urls)),

    # Ruta específica para tu Dashboard visual
    path('dashboard/', dashboard_entrenador, name='dashboard_entrenador'),
]