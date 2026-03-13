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
from .integration_views import IntegrationStartView, IntegrationStatusView, CoachAthleteIntegrationStatusView, ProviderStatusView, IntegrationDisconnectView
from .integration_callback_views import IntegrationCallbackView
from .identity_views import UserIdentityView
from .connection_views import ProviderConnectionStatusView  # PR11
from core.webhooks import StravaWebhookView, StravaDiagnosticsView  # PR-WebhookRoute
from core.views_p1 import (  # PR-115/116/117/119/128
    AthleteAdherenceViewSet,
    AthleteGoalViewSet,
    AthleteProfileViewSet,
    PlannedWorkoutViewSet,
    RaceEventViewSet,
    ReconciliationViewSet,
    WorkoutAssignmentViewSet,
    WorkoutLibraryViewSet,
)

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
from .views import AlumnoPlannedWorkoutViewSet

urlpatterns = [
    # Canonical user identity endpoint
    path('me', UserIdentityView.as_view(), name='user_identity'),

    # PR-WebhookRoute: Strava webhook at the URL Strava calls for push_subscriptions
    # GET  → hub.challenge echo (subscription verification, AllowAny, CSRF-exempt)
    # POST → event ingestion (idempotent, AllowAny, CSRF-exempt)
    path('integrations/strava/webhook/', StravaWebhookView.as_view(), name='strava_webhook_api'),
    path('integrations/strava/diagnostics/', StravaDiagnosticsView.as_view(), name='strava_diagnostics'),

    # PR3: Canonical Nested Planned Workouts
    path('alumnos/<int:alumno_id>/planned-workouts/', 
         AlumnoPlannedWorkoutViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='alumno-planned-workouts-list'),
    path('alumnos/<int:alumno_id>/planned-workouts/<int:pk>/', 
         AlumnoPlannedWorkoutViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), 
         name='alumno-planned-workouts-detail'),

    # PR3: Compat Alias (same viewset)
    path('athletes/<int:athlete_id>/planned-workouts/', 
         AlumnoPlannedWorkoutViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='athlete-planned-workouts-list'),
    path('athletes/<int:athlete_id>/planned-workouts/<int:pk>/', 
         AlumnoPlannedWorkoutViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), 
         name='athlete-planned-workouts-detail'),
    
    # OAuth Integration Management
    
    # OAuth Integration Management
    path('integrations/<str:provider>/start', IntegrationStartView.as_view(), name='integration_start'),
    path('integrations/<str:provider>/callback', IntegrationCallbackView.as_view(), name='integration_callback'),
    path('integrations/<str:provider>/disconnect/', IntegrationDisconnectView.as_view(), name='integration_disconnect'),
    path('integrations/<str:provider>/status', ProviderStatusView.as_view(), name='provider_status'),  # NEW: Provider-specific status
    path('integrations/status', IntegrationStatusView.as_view(), name='integration_status'),  # All providers status

    # PR11: Non-Strava provider connection status (derived from OAuthCredential)
    path('connections/', ProviderConnectionStatusView.as_view(), name='provider_connections'),

    # Coach-scoped integration status
    path('coach/athletes/<int:alumno_id>/integrations/status', CoachAthleteIntegrationStatusView.as_view(), name='coach_athlete_integration_status'),
    
    # Rutas automáticas de la API (GET, POST, PUT, DELETE)
    # Ejemplo: /api/equipos/, /api/alumnos/, /api/upload-video/
    path('', include(router.urls)),

    # Ruta específica para tu Dashboard visual (Vista Legacy de Django)
    path('dashboard/', dashboard_entrenador, name='dashboard_entrenador'),

    # ==============================================================================
    # PR-115: P1 organization-first API — RaceEvent + AthleteGoal
    # URL pattern: /api/p1/orgs/<org_id>/race-events/  and  /api/p1/orgs/<org_id>/goals/
    # organization is resolved from the URL, never from the request body.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/race-events/',
        RaceEventViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-race-event-list',
    ),
    path(
        'p1/orgs/<int:org_id>/race-events/<int:pk>/',
        RaceEventViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-race-event-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/goals/',
        AthleteGoalViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-goal-list',
    ),
    path(
        'p1/orgs/<int:org_id>/goals/<int:pk>/',
        AthleteGoalViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-goal-detail',
    ),

    # ==============================================================================
    # PR-116: P1 organization-first API — AthleteProfile
    # URL pattern: /api/p1/orgs/<org_id>/profiles/
    # Lookup by athlete_id (OneToOne FK column), not by profile PK.
    # No DELETE — profile deletion is out of scope for this PR.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/profiles/',
        AthleteProfileViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-profile-list',
    ),
    path(
        'p1/orgs/<int:org_id>/profiles/<int:athlete_id>/',
        AthleteProfileViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
        }),
        name='p1-profile-detail',
    ),

    # ==============================================================================
    # PR-117: P1 organization-first API — WorkoutAssignment
    # URL pattern: /api/p1/orgs/<org_id>/assignments/
    # organization is resolved from the URL, never from the request body.
    # No DELETE — use status="canceled" to retire an assignment.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/assignments/',
        WorkoutAssignmentViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-assignment-list',
    ),
    path(
        'p1/orgs/<int:org_id>/assignments/<int:pk>/',
        WorkoutAssignmentViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
        }),
        name='p1-assignment-detail',
    ),

    # ==============================================================================
    # PR-119: P1 organization-first API — WorkoutReconciliation
    # Nested under assignments: /api/p1/orgs/<org_id>/assignments/<assignment_id>/reconciliation/
    # State transitions via POST actions; no DELETE; no direct write surface.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/assignments/<int:assignment_id>/reconciliation/',
        ReconciliationViewSet.as_view({'get': 'retrieve'}),
        name='p1-reconciliation-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/assignments/<int:assignment_id>/reconciliation/reconcile/',
        ReconciliationViewSet.as_view({'post': 'reconcile'}),
        name='p1-reconciliation-reconcile',
    ),
    path(
        'p1/orgs/<int:org_id>/assignments/<int:assignment_id>/reconciliation/miss/',
        ReconciliationViewSet.as_view({'post': 'miss'}),
        name='p1-reconciliation-miss',
    ),

    # ==============================================================================
    # PR-128: WorkoutLibrary CRUD
    # URL: /api/p1/orgs/<org_id>/libraries/
    # Nested workouts: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/libraries/',
        WorkoutLibraryViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-library-list',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:pk>/',
        WorkoutLibraryViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-library-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/',
        PlannedWorkoutViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-library-workout-list',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/<int:pk>/',
        PlannedWorkoutViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-library-workout-detail',
    ),

    # ==============================================================================
    # PR-119: P1 organization-first API — Athlete Weekly Adherence
    # URL: /api/p1/orgs/<org_id>/athletes/<athlete_id>/adherence/
    # Query param: week_start=YYYY-MM-DD (required)
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/adherence/',
        AthleteAdherenceViewSet.as_view({'get': 'retrieve'}),
        name='p1-athlete-adherence',
    ),
]