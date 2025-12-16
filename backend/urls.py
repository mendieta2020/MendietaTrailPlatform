# backend/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Importamos la vista del dashboard directamente (Vista Clásica)
from core.views import dashboard_entrenador

# --- Importamos el Webhook Listener ---
from core.webhooks import strava_webhook

# --- Importaciones para Documentación (Swagger) y Autenticación (JWT) ---
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
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
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # 1. Panel de Administración de Django
    path('admin/', admin.site.urls),
    
    # 2. LOGIN SOCIAL (STRAVA/ALLAUTH)
    path('accounts/', include('allauth.urls')), 

    # 3. Herramientas Administrativas (Nested Admin)
    path('_nested_admin/', include('nested_admin.urls')),

    # 4. Dashboard del Entrenador (Vista Legacy/Django Template)
    path('dashboard/', dashboard_entrenador, name='dashboard_principal'),

    # ==============================================================
    # 5. WEBHOOKS (La "Oreja" del sistema)
    # ==============================================================
    path('webhooks/strava/', strava_webhook, name='strava_webhook'),

    # ==============================================================
    # 6. API REST ENDPOINTS (El Corazón del SaaS React)
    # ==============================================================
    
    # 🔥 AQUÍ VIAJAN LOS DATOS DE ENTRENAMIENTO Y VIDEOS 🔥
    path('api/', include('core.urls')), 

    # Rutas de Analytics (Ciencia de Datos, PMC, Widgets)
    path('api/analytics/', include('analytics.urls')),

    # ==============================================================

    # 7. Autenticación (Tokens JWT)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 8. Documentación Interactiva (Swagger)
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

# --- CONFIGURACIÓN PARA SERVIR ARCHIVOS EN MODO DESARROLLO ---
# ⚠️ CRÍTICO: Esto permite que el Frontend reproduzca los videos subidos
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)