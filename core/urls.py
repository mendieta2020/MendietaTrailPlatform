from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AlumnoViewSet, 
    EntrenamientoViewSet, 
    PlantillaViewSet,
    CarreraViewSet,
    InscripcionViewSet,
    PagoViewSet,
    EquipoViewSet, 
    VideoUploadViewSet, # <--- 1. IMPORTANTE: Importamos el Gestor de Videos
    ActividadViewSet,
    dashboard_entrenador
)
from .integration_views import IntegrationStartView, IntegrationStatusView

# Creamos el router para la API REST estándar
router = DefaultRouter()

# ==============================================================================
#  RUTAS DEL NÚCLEO (CORE) - API ENDPOINTS
# ==============================================================================

# 1. Gestión de Personas y Grupos
router.register(r'equipos', EquipoViewSet, basename='equipo')
router.register(r'alumnos', AlumnoViewSet, basename='alumno')
# Alias compat/UX: /api/athletes/ (mismo recurso que alumnos)
router.register(r'athletes', AlumnoViewSet, basename='athlete')

# 2. Gestión Operativa (Día a Día)
router.register(r'entrenamientos', EntrenamientoViewSet, basename='entrenamiento')

# 3. Librería de Conocimiento (Recetas)
router.register(r'plantillas', PlantillaViewSet, basename='plantilla')

# 4. Gestión de Eventos (Carreras y Objetivos)
router.register(r'carreras', CarreraViewSet, basename='carrera')
router.register(r'inscripciones', InscripcionViewSet, basename='inscripcion')

# 5. Finanzas y Negocio
router.register(r'pagos', PagoViewSet, basename='pago')

# 5.5. Actividades importadas (Strava → Actividad)
router.register(r'activities', ActividadViewSet, basename='activities')

# 6. Multimedia y Herramientas (Gimnasio Pro)
# Esta es la ruta que usa el botón de la cámara en el Frontend
router.register(r'upload-video', VideoUploadViewSet, basename='upload-video') 

urlpatterns = [
    # OAuth Integration Management
    path('integrations/<str:provider>/start', IntegrationStartView.as_view(), name='integration_start'),
    path('integrations/status', IntegrationStatusView.as_view(), name='integration_status'),
    
    # Rutas automáticas de la API (GET, POST, PUT, DELETE)
    # Ejemplo: /api/equipos/, /api/alumnos/, /api/upload-video/
    path('', include(router.urls)),

    # Ruta específica para tu Dashboard visual (Vista Legacy de Django)
    path('dashboard/', dashboard_entrenador, name='dashboard_entrenador'),
]