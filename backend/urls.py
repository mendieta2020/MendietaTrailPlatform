# backend/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Importamos la vista del dashboard directamente
from core.views import dashboard_entrenador

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
    # Esta línea es CRUCIAL: Habilita las rutas /accounts/login, /accounts/strava/login, etc.
    # Sin esto, el botón "Conectar Strava" en el dashboard dará error.
    path('accounts/', include('allauth.urls')), 

    # 3. Herramientas Administrativas (Nested Admin)
    path('_nested_admin/', include('nested_admin.urls')),

    # 4. Dashboard del Entrenador
    # Ruta directa para ver el panel visual
    path('dashboard/', dashboard_entrenador, name='dashboard_principal'),

    # 5. La API del Core (Endpoints para datos)
    path('api/', include('core.urls')),

    # 6. Autenticación (Tokens JWT)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 7. Documentación Interactiva (Swagger)
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

# Configuración para servir archivos estáticos en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)