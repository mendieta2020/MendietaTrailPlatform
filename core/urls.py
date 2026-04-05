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
from core.views_billing import (  # PR-131 / PR-132 / PR-134 / PR-135 / PR-136 / PR-137 / PR-150
    mercadopago_webhook,
    AthleteSubscriptionWebhookView,
    BillingStatusView,
    BillingSubscribeView,
    BillingCancelView,
    MPConnectView,
    MPCallbackView,
    MPDisconnectView,
    InvitationCreateView,
    InvitationDetailView,
    InvitationAcceptView,
    InvitationRejectView,
    InvitationResendView,
    CoachPricingPlanListCreateView,
    AthleteSubscriptionListView,
    AthleteSubscriptionActivateView,
    InviteLinkView,
    InviteLinkRegenerateView,
    JoinDetailView,
    AthleteMySubscriptionView,
    CoachPricingPlanDetailView,
    AthletePaymentLinkView,
)
from core.views_p1 import (  # PR-115/116/117/119/128/X4/149/PR-128-real-pmc/PR-129
    AthleteAdherenceViewSet,
    AthleteGoalViewSet,
    AthleteProfileViewSet,
    AthleteRealPMCView,
    DashboardAnalyticsView,
    ExternalIdentityViewSet,
    PlannedWorkoutViewSet,
    RaceEventViewSet,
    ReconciliationViewSet,
    StravaBackfillView,
    WorkoutAssignmentViewSet,
    WorkoutBlockViewSet,
    WorkoutIntervalViewSet,
    AthleteInjuryViewSet,
    AthleteAvailabilityListView,
    WorkoutLibraryViewSet,
    WellnessCheckInViewSet,
    WellnessDismissView,
    TrainingWeekViewSet,
)
from core.views_pmc import (  # PR-128a / PR-145a / PR-152
    AthletePMCView,
    AthleteHRProfileView,
    CoachAthletePMCView,
    ComplianceView,
    PaceZonesView,
    TeamReadinessView,
    TrainingVolumeView,
    WellnessHistoryView,
)
from core.views_reports import (  # PR-154
    CreateReportView,
    EmailReportView,
)
from core.views_athlete import (  # PR-139 / PR-141 / PR-156
    AthleteTodayView,
    AthleteDeviceStatusView,
    AthleteDevicePreferenceDismissView,
    AthleteDevicePreferenceReactivateView,
    AthleteGoalsView,
    AthleteNotificationListView,
    AthleteNotificationMarkReadView,
    AthleteWeeklySummaryView,
    AthleteWellnessTodayView,
)
from core.views_p1_roster import (  # PR-129 / PR-141 / PR-148 / PR-165a
    AthleteCoachAssignmentViewSet,
    AthleteRosterViewSet,
    CoachBriefingView,
    CoachNotifyAthleteDeviceView,
    CoachViewSet,
    MembershipViewSet,
    TeamInvitationViewSet,
    TeamMembersView,
    TeamViewSet,
)
from core.views_messages import (  # PR-147
    InternalMessageListCreateView,
    InternalMessageMarkReadView,
    AthleteAlertsView,
)
from core.views_onboarding import (  # PR-149 / PR-165a
    RegisterView,
    GoogleAuthView,
    OnboardingCompleteView,
    TeamJoinView,
)
from core.views_periodization import (  # PR-157
    AutoPeriodizeAthleteView,
    AutoPeriodizeGroupView,
    AthleteTrainingPhasesView,
    CoachAthleteTrainingPhasesView,
    RecentWorkoutsView,
)
from core.views_planning import (  # PR-158
    WorkoutHistoryView,
    GroupWorkoutHistoryView,
    CopyWeekView,
    EstimatedWeeklyLoadView,
    AthletePlanVsRealView,
    GroupWeekTemplateView,
)
from core.views_athlete_card import (  # PR-159 / PR-161
    CoachAthleteProfileView,
    CoachAthleteInjuriesView,
    CoachAthleteInjuryDetailView,
    CoachAthleteGoalsView,
    CoachAthleteNotesView,
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

    # PR-131: MercadoPago subscription webhook (B2B — Quantoryn org billing)
    path('webhooks/mercadopago/', mercadopago_webhook, name='mp-webhook'),

    # PR-136: MercadoPago athlete subscription webhook (coach→athlete payment sync)
    path('webhooks/mercadopago/athlete/', AthleteSubscriptionWebhookView.as_view(), name='mp-athlete-webhook'),

    # PR-132: Billing views — checkout flow + status
    path('billing/status/', BillingStatusView.as_view(), name='billing-status'),
    path('billing/subscribe/', BillingSubscribeView.as_view(), name='billing-subscribe'),
    path('billing/cancel/', BillingCancelView.as_view(), name='billing-cancel'),

    # PR-134: Coach MP OAuth connect / callback / disconnect
    path('billing/mp/connect/', MPConnectView.as_view(), name='billing-mp-connect'),
    path('billing/mp/callback/', MPCallbackView.as_view(), name='billing-mp-callback'),
    path('billing/mp/disconnect/', MPDisconnectView.as_view(), name='billing-mp-disconnect'),

    # PR-137 + PR-151: Coach pricing plans (CRUD)
    path('billing/plans/', CoachPricingPlanListCreateView.as_view(), name='billing-plans'),
    path('billing/plans/<int:pk>/', CoachPricingPlanDetailView.as_view(), name='billing-plan-detail'),

    # PR-137: Athlete subscriptions list + manual activation
    path('billing/athlete-subscriptions/', AthleteSubscriptionListView.as_view(), name='billing-athlete-subscriptions'),
    path('billing/athlete-subscriptions/<int:pk>/activate/', AthleteSubscriptionActivateView.as_view(), name='billing-athlete-subscription-activate'),

    # PR-135: AthleteInvitation — create/list, detail, accept, reject, resend
    path('billing/invitations/', InvitationCreateView.as_view(), name='billing-invitation-create'),
    path('billing/invitations/<uuid:token>/', InvitationDetailView.as_view(), name='billing-invitation-detail'),
    path('billing/invitations/<uuid:token>/accept/', InvitationAcceptView.as_view(), name='billing-invitation-accept'),
    path('billing/invitations/<uuid:token>/reject/', InvitationRejectView.as_view(), name='billing-invitation-reject'),
    path('billing/invitations/<uuid:token>/resend/', InvitationResendView.as_view(), name='billing-invitation-resend'),

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
    # IMPORTANT: static paths must come before dynamic <str:provider> patterns to avoid shadowing.
    path('integrations/status', IntegrationStatusView.as_view(), name='integration_status'),  # All providers status
    path('integrations/<str:provider>/start', IntegrationStartView.as_view(), name='integration_start'),
    path('integrations/<str:provider>/callback', IntegrationCallbackView.as_view(), name='integration_callback'),
    path('integrations/<str:provider>/disconnect/', IntegrationDisconnectView.as_view(), name='integration_disconnect'),
    path('integrations/<str:provider>/status', ProviderStatusView.as_view(), name='provider_status'),  # Per-provider status

    # PR11: Non-Strava provider connection status (derived from OAuthCredential)
    path('connections/', ProviderConnectionStatusView.as_view(), name='provider_connections'),

    # PR-139: Athlete today's workout
    path('athlete/today/', AthleteTodayView.as_view(), name='athlete-today'),

    # PR-128a: PMC endpoints (athlete self-service + coach views)
    path('athlete/pmc/', AthletePMCView.as_view(), name='athlete-pmc'),
    path('athlete/hr-profile/', AthleteHRProfileView.as_view(), name='athlete-hr-profile'),
    path('athlete/pace-zones/', PaceZonesView.as_view(), name='athlete-pace-zones'),
    path('coach/athletes/<int:membership_id>/pmc/', CoachAthletePMCView.as_view(), name='coach-athlete-pmc'),
    path('coach/team-readiness/', TeamReadinessView.as_view(), name='coach-team-readiness'),

    # PR-152: Athlete detail views — training volume, wellness, compliance
    path('coach/athletes/<int:membership_id>/training-volume/', TrainingVolumeView.as_view(), name='coach-athlete-training-volume'),
    path('coach/athletes/<int:membership_id>/wellness/', WellnessHistoryView.as_view(), name='coach-athlete-wellness'),
    path('coach/athletes/<int:membership_id>/compliance/', ComplianceView.as_view(), name='coach-athlete-compliance'),

    # PR-159: Athlete Card — profile, injuries, goals, notes
    path('coach/athletes/<int:membership_id>/profile/', CoachAthleteProfileView.as_view(), name='coach-athlete-profile'),
    path('coach/athletes/<int:membership_id>/card-injuries/', CoachAthleteInjuriesView.as_view(), name='coach-athlete-card-injuries'),
    path('coach/athletes/<int:membership_id>/card-injuries/<int:pk>/', CoachAthleteInjuryDetailView.as_view(), name='coach-athlete-card-injury-detail'),
    path('coach/athletes/<int:membership_id>/card-goals/', CoachAthleteGoalsView.as_view(), name='coach-athlete-card-goals'),
    path('coach/athletes/<int:membership_id>/notes/', CoachAthleteNotesView.as_view(), name='coach-athlete-notes'),

    # PR-154: Shareable athlete reports
    path('coach/athletes/<int:membership_id>/report/', CreateReportView.as_view(), name='coach-create-report'),
    path('coach/athletes/<int:membership_id>/report/<str:token>/email/', EmailReportView.as_view(), name='coach-email-report'),

    # PR-141: Athlete device status + preference + notifications
    path('athlete/device-status/', AthleteDeviceStatusView.as_view(), name='athlete-device-status'),
    path('athlete/device-preference/dismiss/', AthleteDevicePreferenceDismissView.as_view(), name='athlete-device-preference-dismiss'),
    path('athlete/device-preference/reactivate/', AthleteDevicePreferenceReactivateView.as_view(), name='athlete-device-preference-reactivate'),
    path('athlete/notifications/', AthleteNotificationListView.as_view(), name='athlete-notifications'),
    path('athlete/notifications/<int:pk>/mark-read/', AthleteNotificationMarkReadView.as_view(), name='athlete-notification-mark-read'),

    # PR-156: Athlete self-serve progress endpoints
    path('athlete/goals/', AthleteGoalsView.as_view(), name='athlete-goals'),
    path('athlete/weekly-summary/', AthleteWeeklySummaryView.as_view(), name='athlete-weekly-summary'),
    path('athlete/wellness/today/', AthleteWellnessTodayView.as_view(), name='athlete-wellness-today'),

    # PR-157: Auto-periodization
    path('coach/athletes/<int:membership_id>/auto-periodize/', AutoPeriodizeAthleteView.as_view(), name='coach-auto-periodize-athlete'),
    path('coach/athletes/<int:membership_id>/recent-workouts/', RecentWorkoutsView.as_view(), name='coach-recent-workouts'),
    path('athlete/training-phases/', AthleteTrainingPhasesView.as_view(), name='athlete-training-phases'),
    path('p1/orgs/<int:org_id>/auto-periodize-group/', AutoPeriodizeGroupView.as_view(), name='p1-auto-periodize-group'),
    path('p1/orgs/<int:org_id>/athletes/<int:athlete_id>/training-phases/', CoachAthleteTrainingPhasesView.as_view(), name='p1-athlete-training-phases'),

    # PR-158: Planificador Pro — workout history, copy-week, estimated load, plan vs real
    path('coach/athletes/<int:membership_id>/workout-history/', WorkoutHistoryView.as_view(), name='coach-workout-history'),
    path('coach/athletes/<int:membership_id>/estimated-weekly-load/', EstimatedWeeklyLoadView.as_view(), name='coach-estimated-weekly-load'),
    path('p1/orgs/<int:org_id>/group-workout-history/', GroupWorkoutHistoryView.as_view(), name='p1-group-workout-history'),
    path('p1/orgs/<int:org_id>/copy-week/', CopyWeekView.as_view(), name='p1-copy-week'),
    path('athlete/plan-vs-real/', AthletePlanVsRealView.as_view(), name='athlete-plan-vs-real'),
    # PR-158 hotfix: Group Planning View template
    path('p1/orgs/<int:org_id>/group-week-template/', GroupWeekTemplateView.as_view(), name='p1-group-week-template'),

    # PR-141: Coach notify athlete to connect device
    path('coach/roster/<int:membership_id>/notify-device/', CoachNotifyAthleteDeviceView.as_view(), name='coach-notify-athlete-device'),

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
            'delete': 'destroy',  # PR-145f
        }),
        name='p1-assignment-detail',
    ),
    # PR-137: SuuntoPlus Guide push action
    path(
        'p1/orgs/<int:org_id>/assignments/<int:pk>/push/',
        WorkoutAssignmentViewSet.as_view({'post': 'push'}),
        name='p1-assignment-push',
    ),
    # PR-145f: Clone workout for per-assignment editing
    path(
        'p1/orgs/<int:org_id>/assignments/<int:pk>/clone-workout/',
        WorkoutAssignmentViewSet.as_view({'post': 'clone_workout'}),
        name='p1-assignment-clone-workout',
    ),
    # PR-145f-fix2: Update snapshot workout (library-agnostic PATCH)
    path(
        'p1/orgs/<int:org_id>/assignments/<int:pk>/update-snapshot/',
        WorkoutAssignmentViewSet.as_view({'patch': 'update_snapshot'}),
        name='p1-assignment-update-snapshot',
    ),
    # PR-145g: Coach post-session comment
    path(
        'p1/orgs/<int:org_id>/assignments/<int:pk>/coach-comment/',
        WorkoutAssignmentViewSet.as_view({'patch': 'add_coach_comment'}),
        name='p1-assignment-coach-comment',
    ),
    # PR-145: Bulk team workout assignment
    path(
        'p1/orgs/<int:org_id>/assignments/bulk-assign-team/',
        WorkoutAssignmentViewSet.as_view({'post': 'bulk_assign_team'}),
        name='p1-assignment-bulk-assign-team',
    ),
    # PR-145h: Bulk create by athlete_ids
    path(
        'p1/orgs/<int:org_id>/assignments/bulk-create/',
        WorkoutAssignmentViewSet.as_view({'post': 'bulk_create'}),
        name='p1-assignment-bulk-create',
    ),
    # PR-145f: Copy week
    path(
        'p1/orgs/<int:org_id>/assignments/copy-week/',
        WorkoutAssignmentViewSet.as_view({'post': 'copy_week'}),
        name='p1-assignment-copy-week',
    ),
    # PR-145f: Delete week
    path(
        'p1/orgs/<int:org_id>/assignments/delete-week/',
        WorkoutAssignmentViewSet.as_view({'post': 'delete_week'}),
        name='p1-assignment-delete-week',
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
    # PR-128b: WorkoutBlock + WorkoutInterval CRUD
    # URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/blocks/
    # Nested intervals: .../blocks/<block_id>/intervals/
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/<int:workout_id>/blocks/',
        WorkoutBlockViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-workout-block-list',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/<int:workout_id>/blocks/<int:pk>/',
        WorkoutBlockViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-workout-block-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/<int:workout_id>/blocks/<int:block_id>/intervals/',
        WorkoutIntervalViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-workout-interval-list',
    ),
    path(
        'p1/orgs/<int:org_id>/libraries/<int:library_id>/workouts/<int:workout_id>/blocks/<int:block_id>/intervals/<int:pk>/',
        WorkoutIntervalViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-workout-interval-detail',
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

    # PR-153: Athlete injuries + availability
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/injuries/',
        AthleteInjuryViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-athlete-injuries-list',
    ),
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/injuries/<int:pk>/',
        AthleteInjuryViewSet.as_view({
            'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
        }),
        name='p1-athlete-injuries-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/availability/',
        AthleteAvailabilityListView.as_view({'get': 'list', 'put': 'bulk_update'}),
        name='p1-athlete-availability',
    ),

    # PR-155: TrainingWeek — macro periodization view
    path(
        'p1/orgs/<int:org_id>/training-weeks/',
        TrainingWeekViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-training-weeks',
    ),

    # PR-154: Wellness check-in
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/wellness/',
        WellnessCheckInViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-athlete-wellness-list',
    ),
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/wellness/dismiss/',
        WellnessDismissView.as_view(),
        name='p1-athlete-wellness-dismiss',
    ),

    # ==============================================================================
    # PR-128: Real-side PMC (CTL/ATL/TSB) from CompletedActivity
    # URL: /api/p1/orgs/<org_id>/athletes/<athlete_id>/pmc/real/
    # Read-only. Owner/coach: any athlete. Athlete: own only (404 if other).
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/pmc/real/',
        AthleteRealPMCView.as_view(),
        name='p1-athlete-pmc-real',
    ),

    # ==============================================================================
    # PR-129: Strava historical backfill
    # URL: POST /api/p1/orgs/<org_id>/athletes/<athlete_id>/backfill/strava/
    # Returns 202 immediately; backfill runs async in a Celery worker.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/backfill/strava/',
        StravaBackfillView.as_view(),
        name='p1-athlete-strava-backfill',
    ),

    # ==============================================================================
    # PR-129: Roster API — Coach, Athlete (roster), Team, Membership,
    #         AthleteCoachAssignment
    # All routes are organization-scoped: org is derived from org_id in the URL,
    # never from the request body.
    # NOTE: AthleteRosterViewSet uses /roster/athletes/ to avoid collision with
    #       the existing /athletes/<athlete_id>/adherence/ route above.
    # ==============================================================================

    # Coach CRUD
    path(
        'p1/orgs/<int:org_id>/coaches/',
        CoachViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-coach-list',
    ),
    path(
        'p1/orgs/<int:org_id>/coaches/<int:pk>/',
        CoachViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-coach-detail',
    ),

    # Athlete Roster CRUD
    path(
        'p1/orgs/<int:org_id>/roster/athletes/',
        AthleteRosterViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-roster-athlete-list',
    ),
    path(
        'p1/orgs/<int:org_id>/roster/athletes/<int:pk>/',
        AthleteRosterViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-roster-athlete-detail',
    ),

    # Team CRUD
    path(
        'p1/orgs/<int:org_id>/teams/',
        TeamViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-team-list',
    ),
    path(
        'p1/orgs/<int:org_id>/teams/<int:pk>/',
        TeamViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-team-detail',
    ),
    # Team members CRUD (PR-145h)
    path(
        'p1/orgs/<int:org_id>/teams/<int:pk>/members/',
        TeamViewSet.as_view({'get': 'members', 'post': 'members'}),
        name='p1-team-members',
    ),
    path(
        'p1/orgs/<int:org_id>/teams/<int:pk>/members/<int:athlete_id>/',
        TeamViewSet.as_view({'delete': 'remove_member'}),
        name='p1-team-members-detail',
    ),
    # Team compliance week (PR-145h)
    path(
        'p1/orgs/<int:org_id>/teams/<int:pk>/compliance-week/',
        TeamViewSet.as_view({'get': 'compliance_week'}),
        name='p1-team-compliance-week',
    ),

    # Membership (no destroy)
    path(
        'p1/orgs/<int:org_id>/memberships/',
        MembershipViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-membership-list',
    ),
    path(
        'p1/orgs/<int:org_id>/memberships/<int:pk>/',
        MembershipViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
        }),
        name='p1-membership-detail',
    ),

    # AthleteCoachAssignment (list, create, retrieve, end)
    path(
        'p1/orgs/<int:org_id>/coach-assignments/',
        AthleteCoachAssignmentViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-coach-assignment-list',
    ),
    path(
        'p1/orgs/<int:org_id>/coach-assignments/<int:pk>/',
        AthleteCoachAssignmentViewSet.as_view({'get': 'retrieve'}),
        name='p1-coach-assignment-detail',
    ),
    path(
        'p1/orgs/<int:org_id>/coach-assignments/<int:pk>/end/',
        AthleteCoachAssignmentViewSet.as_view({'post': 'end'}),
        name='p1-coach-assignment-end',
    ),

    # ==============================================================================
    # PR-149: Dashboard Analytics
    # URL: /api/p1/orgs/<org_id>/dashboard-analytics/
    # Read-only. Owner/coach only.
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/dashboard-analytics/',
        DashboardAnalyticsView.as_view(),
        name='p1-dashboard-analytics',
    ),

    # PR-X4: ExternalIdentity Linking API
    # URL: /api/p1/orgs/<org_id>/external-identities/
    path(
        'p1/orgs/<int:org_id>/external-identities/',
        ExternalIdentityViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='p1-external-identity-list',
    ),
    path(
        'p1/orgs/<int:org_id>/external-identities/<int:pk>/',
        ExternalIdentityViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='p1-external-identity-detail',
    ),

    # ==============================================================================
    # PR-148: Coach morning briefing
    path(
        'p1/orgs/<int:org_id>/coach-briefing/',
        CoachBriefingView.as_view(),
        name='p1-coach-briefing',
    ),

    # PR-150: Universal invite link + athlete subscription
    path('billing/invite-link/', InviteLinkView.as_view(), name='billing-invite-link'),
    path('billing/invite-link/regenerate/', InviteLinkRegenerateView.as_view(), name='billing-invite-link-regenerate'),
    path('billing/join/<str:slug>/', JoinDetailView.as_view(), name='billing-join-detail'),
    path('athlete/subscription/', AthleteMySubscriptionView.as_view(), name='athlete-subscription'),
    path('athlete/payment-link/', AthletePaymentLinkView.as_view(), name='athlete-payment-link'),

    # PR-149: Athlete registration + onboarding
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/google/', GoogleAuthView.as_view(), name='auth-google'),
    path('onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete'),

    # PR-165a: Team invitations (owner creates/revokes; owner+coach lists)
    path('p1/orgs/<int:org_id>/invitations/team/', TeamInvitationViewSet.as_view({'get': 'list', 'post': 'create'}), name='team-invitations'),
    path('p1/orgs/<int:org_id>/invitations/team/<int:pk>/', TeamInvitationViewSet.as_view({'delete': 'destroy'}), name='team-invitation-detail'),
    # PR-165a Fix 2: Team members from Membership (owner/coach/staff)
    path('p1/orgs/<int:org_id>/team-members/', TeamMembersView.as_view(), name='team-members'),
    # PR-165a: Public team join endpoint (preview GET + accept POST)
    path('team-join/<uuid:token>/', TeamJoinView.as_view(), name='team-join'),

    # PR-147: Internal Messages & Smart Alerts
    # URL: /api/p1/orgs/<org_id>/messages/
    #      /api/p1/orgs/<org_id>/messages/<id>/read/
    #      /api/p1/orgs/<org_id>/athletes/<athlete_id>/alerts/
    # ==============================================================================
    path(
        'p1/orgs/<int:org_id>/messages/',
        InternalMessageListCreateView.as_view(),
        name='p1-messages-list-create',
    ),
    path(
        'p1/orgs/<int:org_id>/messages/<int:pk>/read/',
        InternalMessageMarkReadView.as_view(),
        name='p1-messages-mark-read',
    ),
    path(
        'p1/orgs/<int:org_id>/athletes/<int:athlete_id>/alerts/',
        AthleteAlertsView.as_view(),
        name='p1-athlete-alerts',
    ),
]