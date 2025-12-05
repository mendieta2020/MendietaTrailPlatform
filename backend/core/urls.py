from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlumnoViewSet, EntrenamientoViewSet, dashboard_entrenador # <--- Importante importar esto

router = DefaultRouter()
router.register(r'alumnos', AlumnoViewSet)
router.register(r'entrenamientos', EntrenamientoViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    # Esta es la línea clave, asegúrate de que apunte a dashboard_entrenador
    path('dashboard/', dashboard_entrenador, name='dashboard'), 
]