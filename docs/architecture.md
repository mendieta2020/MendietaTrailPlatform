# Arquitectura crítica & guardrails (PR0)

## Visión general
- **backend/**: núcleo Django/DRF (API, auth, permisos, multi-tenant, ingestión Strava).
- **core/**: dominio principal (Actividades, Entrenamientos, Strava, servicios, tareas Celery).
- **analytics/**: capa de ciencia (PMC/CTL-ATL-TSB, carga canónica, alertas, injury risk).

**Flujo alto nivel**: Strava → webhook → `StravaWebhookEvent` → Celery → `Actividad` → agregaciones/PMC en `analytics`.

## Source of Truth & Strava pipeline
- **Único camino operativo**: webhook → `StravaWebhookEvent` → task Celery → `Actividad`.
- **Pipeline legacy bloqueado**: `sincronizar_actividades_strava` está deshabilitado por defecto.
  - Se habilita sólo cambiando `DISABLE_LEGACY_STRAVA_SYNC=False` en entorno.
- **SoT de ingestión**: `StravaWebhookEvent` (estado, attempts, updated_at) es la fuente de verdad para auditoría/reintentos.
- **Idempotencia/dedupe**: ingestión evita duplicados (evento + actividad se procesan con guardas e `update_or_create`).

## Tenant safety (multi-tenant)
- **`TenantModelViewSet`** aplica filtrado por tenant a nivel queryset.
- Determinación de tenant:
  - Alumno: `usuario=user` o `alumno__usuario=user`.
  - Coach: `entrenador=user`, `uploaded_by=user`, `alumno__entrenador=user`, `usuario=user`, `equipo__entrenador=user`.
- **Invariante clave**: un request autenticado **nunca** puede ver datos de otro coach.
- **Fail-closed**: si no se puede determinar el tenant, se responde 403/404 (nunca `.all()`).

## Auth & seguridad
- **JWT dual mode**:
  - Legacy: `Authorization: Bearer <token>` (soportado).
  - Nuevo: cookies HttpOnly `mt_access` / `mt_refresh`.
- Flags: `USE_COOKIE_AUTH` (backend) y `VITE_USE_COOKIE_AUTH` (frontend).
- En producción: se espera `Secure=True` en cookies y CORS/CSRF configurados por entorno.
- **Invariante**: tokens nunca se exponen en respuestas públicas.
- **Privacidad**: `datos_brutos` sólo se expone en endpoints raw y para staff.

## Ciencia: carga canónica
- `calcular_carga_canonica` usa `LOAD_DEFINITION_VERSION = "1.0"`.
- Prioridad de carga (mayor → menor):
  1. Power (TSS Power)
  2. GAP/TSS
  3. TRIMP
  4. Relative Effort
  5. RPE
- **Campos canónicos**: `canonical_load`, `canonical_load_method`, `load_version`.
- **Invariante**: toda actividad nueva debe tener carga canónica; analytics/PMC la prioriza.

## Flags & toggles críticos
- `DISABLE_LEGACY_STRAVA_SYNC`: bloquea el pipeline legacy (default **True** en prod).
- `STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES`: umbral para detectar eventos stuck.
- `STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD`: umbral para alertas de fallos.
- `USE_COOKIE_AUTH`: habilita JWT en cookies HttpOnly.
- `VITE_USE_COOKIE_AUTH`: habilita modo cookies en frontend.
- `COOKIE_AUTH_ACCESS_NAME` / `COOKIE_AUTH_REFRESH_NAME`: nombres de cookies.
- `COOKIE_AUTH_SAMESITE` / `COOKIE_AUTH_DOMAIN` / `COOKIE_AUTH_SECURE`: políticas de cookies.
- `LOAD_DEFINITION_VERSION`: versión del cálculo de carga canónica.
