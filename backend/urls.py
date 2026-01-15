# backend/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Importamos la vista del dashboard directamente (Vista Clásica)
from core.views import dashboard_entrenador
from core.strava_oauth_views import oauth2_callback as strava_oauth2_callback
from core.strava_oauth_views import oauth2_login as strava_oauth2_login

# --- Importamos el Webhook Listener ---
from core.webhooks import StravaWebhookView

# --- Importaciones para Documentación (Swagger) y Autenticación (JWT) ---
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from core.permissions import SwaggerAccessPermission
from core.auth_views import (
    CookieLogoutView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    SessionStatusView,
)
from analytics.health_views import (
    healthz,
    healthz_celery,
    healthz_redis,
    healthz_strava,
)

# Configuración de la vista de documentación API
schema_view = get_schema_view(
   openapi.Info(
      title="Mendieta Trail Platform API",
      default_version='v1',
      description="API para gestión de entrenamientos y atletas",
      contact=openapi.Contact(email="admin@mendieta.com"),
      license=openapi.License(name="BSD License"),
   ),
   public=False,
   permission_classes=(SwaggerAccessPermission,),
)

urlpatterns = [
    # 1. Panel de Administración de Django
    path('admin/', admin.site.urls),
    
    # 1.5 LOGIN SOCIAL (STRAVA) - override con logging enriquecido (mismas URLs/names que allauth)
    path('accounts/strava/login/', strava_oauth2_login, name='strava_login'),
    path('accounts/strava/login/callback/', strava_oauth2_callback, name='strava_callback'),

    # 2. LOGIN SOCIAL (STRAVA/ALLAUTH)
    path('accounts/', include('allauth.urls')), 

    # 3. Herramientas Administrativas (Nested Admin)
    path('_nested_admin/', include('nested_admin.urls')),

    # 4. Dashboard del Entrenador (Vista Legacy/Django Template)
    path('dashboard/', dashboard_entrenador, name='dashboard_principal'),

    # ============================================================== 
    # 0. Healthchecks (observabilidad mínima)
    path('healthz', healthz, name='healthz'),
    path('healthz/celery', healthz_celery, name='healthz_celery'),
    path('healthz/redis', healthz_redis, name='healthz_redis'),
    path('healthz/strava', healthz_strava, name='healthz_strava'),

    # ============================================================== 
    # 5. WEBHOOKS (La "Oreja" del sistema)
    # ==============================================================
    path('webhooks/strava/', StravaWebhookView.as_view(), name='strava_webhook'),

    # ==============================================================
    # 6. API REST ENDPOINTS (El Corazón del SaaS React)
    # ==============================================================
    
    # 🔥 AQUÍ VIAJAN LOS DATOS DE ENTRENAMIENTO Y VIDEOS 🔥
    path('api/', include('core.urls')), 

    # Rutas de Analytics (Ciencia de Datos, PMC, Widgets)
    path('api/analytics/', include('analytics.urls')),

    # Coach Decision Layer v1 (coach-first)
    path('api/coach/', include('analytics.coach_urls')),

    # ==============================================================

    # 7. Autenticación (Tokens JWT)
    path('api/token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/logout/', CookieLogoutView.as_view(), name='token_logout'),
    path('api/auth/session/', SessionStatusView.as_view(), name='auth_session'),

    # 8. Documentación Interactiva (Swagger)
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

# --- CONFIGURACIÓN PARA SERVIR ARCHIVOS EN MODO DESARROLLO ---
# ⚠️ CRÍTICO: Esto permite que el Frontend reproduzca los videos subidos
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
