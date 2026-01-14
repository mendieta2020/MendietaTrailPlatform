# AUDIT — MendietaTrailPlatform (2026-01-14)

Auditoría técnica realizada sobre el código disponible en este workspace (**sin modificar código de producción**).  
Stack objetivo: **Django/DRF + Celery/Redis + PostgreSQL + React/Vite + Integración Strava + Analytics endurance**.

---

## 1. Executive Summary

- **Estado general**: la plataforma ya tiene un esqueleto SaaS razonable (DRF cerrado por defecto, multi-tenant coach-scoped, pipeline Strava idempotente, analytics incremental con agregados y PMC).
- **Backbone de analytics**: existe una “línea de producción” clara **Actividad → DailyActivityAgg → PMCHistory/HistorialFitness → InjuryRisk/Alerts/Coach Decisions** con caching por rango en DB.
- **Multi-tenant**: hay un enfoque **fail-closed** en `core.views.TenantModelViewSet` y validaciones explícitas en endpoints analíticos (coach/athlete-scoped).
- **Punto más riesgoso**: **superficie expuesta / hardening** (Swagger público, ausencia de rate limiting, y modo no-cookie con tokens en localStorage).
- **Escalabilidad**: el diseño aguanta “fase inicial” pero con 100k atletas el costo estará dominado por **crecimiento de tablas (raw payloads), recomputes (delete+bulk_create), y presión de colas** si hay backfills masivos.

**Conclusiones clave (3–5)**

1. **PRO**: el pipeline de Strava (webhook thin + event store + lock por actividad + retries + auditoría) es sorprendentemente “production-grade” para un MVP.  
2. **CON**: la plataforma hoy depende de varios “guardrails” (flags/env) para no abrir puertas (swagger/rate limit/tokens). Falta una postura de seguridad *defense-in-depth*.
3. **Multi-tenant**: la base es buena, pero el sistema está cerca de un punto crítico: cualquier APIView nueva sin scoping puede reintroducir fugas; hay que institucionalizar el patrón.
4. **Analytics**: la definición canónica de carga (PR6) existe y se usa; el riesgo principal es **consistencia** (múltiples “loads” coexistiendo) y **coste de recompute** al escalar.
5. **Frontend**: hay UI y paneles claros (Coach Decisions); pero el manejo de sesión en modo JWT header es frágil y el cliente hace “normalización defensiva” que delata contrato inestable.

---

## 2. System Overview

### 2.1 Diagrama textual de componentes

```
React/Vite (frontend/)
  - AuthContext + axios client (token/cookie)
  - Pages: Dashboard, Athletes, AthleteDetail, Teams, Alerts
  - Coach Decisions Panel (week-summary + alerts patch)
        |
        |  HTTP (JWT Bearer or Cookie JWT)  + CORS
        v
Django (backend/)
  - DRF API (/api/*, /api/analytics/*, /api/coach/*)
  - Django Admin (/admin)
  - Swagger UI (/swagger)  [hoy público]
  - Webhooks Strava (/webhooks/strava) -> encola Celery
        |
        |  Celery tasks + Redis broker
        v
Celery/Redis
  - strava.process_event: dedupe + upsert Actividad + plan-vs-actual + enqueue analytics recompute
  - analytics.recompute_pmc_from_activities: rebuild aggs + PMC incremental
        |
        v
PostgreSQL
  - core_* (Alumno, Entrenamiento, Actividad, WebhookEvent, ImportLog, ...)
  - analytics_* (DailyActivityAgg, PMCHistory, InjuryRiskSnapshot, Alerts, Cache, ...)
```

### 2.2 Modelos de negocio (alto nivel)

- **Tenancy (tenant actual = coach)**:
  - `auth.User` (coach o atleta).
  - `core.Alumno` referencia a `entrenador (User)` y opcionalmente a `usuario (User)` si el atleta tiene cuenta.
  - `core.Equipo` pertenece a un `entrenador`.

- **Plan (planificado)**:
  - `core.PlantillaEntrenamiento` (librería de workouts) + `core.PlantillaEntrenamientoVersion` (historial).
  - `core.Entrenamiento` (instancia en calendario del alumno, con `estructura` JSON snapshot).

- **Actual (real)**:
  - `core.Actividad` (fuente de verdad de lo realizado; multi-provider ready; guarda `datos_brutos` para auditoría).
  - Reconciliación hacia `Entrenamiento` (match plan vs real) y persistencia de comparación.

- **Analytics**:
  - `analytics.DailyActivityAgg` (agregado diario por atleta + sport).
  - `analytics.PMCHistory` / `analytics.HistorialFitness` (CTL/ATL/TSB).
  - `analytics.InjuryRiskSnapshot` (riesgo diario).
  - `analytics.SessionComparison` (Plan vs Actual).
  - `analytics.Alert` + `analytics.AnalyticsRangeCache` (coach decisions + cache).

### 2.3 Flujo end-to-end (Usuarios → Auth → Strava → Analytics → Coach Decisions)

1. **Auth**: DRF usa JWT (header) y/o JWT en cookie (`core.authentication.CookieJWTAuthentication`) + `SessionAuthentication`.  
2. **Coach/Atleta**: multi-tenant se deriva de `user` y `user.perfil_alumno` (`core.middleware.TenantContextMiddleware`).
3. **Strava**:
   - OAuth via allauth (`/accounts/...` + overrides en `core/strava_oauth_views`).
   - Webhook: `POST /webhooks/strava/` crea `core.StravaWebhookEvent` idempotente y encola `strava.process_event`.
4. **Ingest**: `core.tasks.process_strava_event`:
   - lock por actividad (`core.StravaActivitySyncState`)
   - resolve identidad (`core.ExternalIdentity` o fallback `Alumno.strava_athlete_id`)
   - normaliza payload, upsert de `core.Actividad`, match/crea `Entrenamiento`, crea `analytics.SessionComparison`, dispara `analytics.alerts`.
5. **Analytics incremental**: `analytics.tasks.recompute_pmc_from_activities`:
   - reconstruye `DailyActivityAgg` desde `Actividad` desde la mínima fecha afectada
   - recalcula PMC (`PMCHistory` + `HistorialFitness`) desde esa fecha
   - (opcional) injury risk daily via beat.
6. **Coach Decisions**: frontend consulta:
   - `/api/coach/athletes/{id}/week-summary/?week=YYYY-Www`
   - patch `/api/coach/alerts/{id}/` para “marcar visto”.

---

## 3. Strengths (Fortalezas)

### 3.1 Arquitectura

- **DRF “cerrado por defecto”**: `REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES = IsAuthenticated` (buena postura base).
- **Multi-tenant fail-closed**: `core.views.TenantModelViewSet` filtra por campos “tenant aware” y **niega (403)** si el modelo no soporta filtro.
- **Separación Plan vs Actual**: `Entrenamiento` (plan) vs `Actividad` (actual) + `SessionComparison` persistido (base sólida para insights).

### 3.2 Diseño de modelos / DB

- **Idempotencia explícita**:
  - `core.StravaWebhookEvent.event_uid` (único) + índices para status/owner/date.
  - `core.Actividad` constraints para `strava_id` y `(source, source_object_id)` (multi-provider ready).
- **Tablas de auditoría operativa**: `core.StravaImportLog` y estados (`StravaWebhookEvent`, `StravaActivitySyncState`, `AthleteSyncState`) facilitan debugging real.

### 3.3 Integración Strava

- **Webhook thin + durable event store** (`core/webhooks.py`) y procesamiento async (`core/tasks.py`) con:
  - dedupe de evento
  - requeue de ciertos estados
  - identidad UNLINKED para no “perder” eventos antes del onboarding
  - retries con backoff y clasificación de errores transitorios.

### 3.4 Analytics (endurance)

- **Materialización incremental**: `DailyActivityAgg` + `PMCHistory` con recompute desde `start_date` (coalescing vía `AthleteSyncState.metrics_pending_from`).
- **Cache persistente por rango**: `analytics.AnalyticsRangeCache` con TTL configurable (reduce recomputes costosos).
- **Coach Decision Layer v1**: triggers accionables en `analytics/alerts.py` (risk+fatigue, compliance drop, acute load spike, etc.).

### 3.5 Frontend

- **Estructura clara** (pages/components/widgets) y panel específico de Coach Decisions.
- **Cliente HTTP con refresh centralizado** (axios interceptors + queue de refresh) y soporte a “modo cookie auth”.

---

## 4. Weaknesses (Debilidades) — con severidad

> Formato: **Área · Severidad** — descripción · archivos/módulos · impacto

1. **Seguridad · High** — Swagger público (`/swagger/`) configurado con `AllowAny`.  
   - **Archivos**: `backend/urls.py` (schema_view), `backend/settings.py`  
   - **Impacto**: enumeración de endpoints/modelos, facilita ataque/abuso en producción.

2. **Seguridad · High** — Falta de rate limiting / throttling a nivel DRF para endpoints sensibles (auth, webhooks, APIs hot).  
   - **Archivos**: `backend/settings.py` (no `DEFAULT_THROTTLE_*`)  
   - **Impacto**: brute force, scraping, DoS por usuarios autenticados, overload de DB/Celery.

3. **Seguridad · High** — En modo “Bearer tokens”, el frontend guarda tokens en **localStorage** (riesgo XSS).  
   - **Archivos**: `frontend/src/api/tokenStore.js`, `frontend/src/api/client.js`  
   - **Impacto**: compromiso de cuenta si se inyecta JS (supply chain, CSP débil, XSS accidental).

4. **Backend/Auth · Medium** — `SIMPLE_JWT.BLACKLIST_AFTER_ROTATION=True` pero no se ve `rest_framework_simplejwt.token_blacklist` en `INSTALLED_APPS`.  
   - **Archivos**: `backend/settings.py`  
   - **Impacto**: expectativa falsa de invalidación de refresh tokens; posible confusión operativa.

5. **Backend/Auth · Medium** — `AuthContext` en modo no-cookie “asume login” si existe access token (no valida sesión ni expira UX).  
   - **Archivos**: `frontend/src/context/AuthContext.jsx`  
   - **Impacto**: UX inconsistente y mayor complejidad para soporte; potencial loop si el token expira.

6. **DB/Integridad · Medium** — `Alumno.entrenador` es nullable; el sistema depende de coach-scoping y muchas queries asumen entrenador.  
   - **Archivos**: `core/models.py`  
   - **Impacto**: datos huérfanos; comportamientos ambiguos; riesgo de fugas si aparecen objetos sin tenant claro.

7. **DB/Integridad · Medium** — `Actividad.usuario` representa “coach propietario del token usado para importar” pero no está garantizado que coincida con `Actividad.alumno.entrenador`.  
   - **Archivos**: `core/models.py`, `core/tasks.py` (upsert usa `usuario=alumno.entrenador`)  
   - **Impacto**: inconsistencias si hay edge cases (cambio de coach, re-linking, imports legacy); complejiza compliance multi-tenant.

8. **Backend/Compatibilidad · Medium** — convivencia de pipelines legacy y nuevo (dashboard con “legacy sync”, servicios legacy con match por email).  
   - **Archivos**: `core/views.py`, `core/services.py`  
   - **Impacto**: riesgo de reactivar flujos inseguros o inconsistentes, y duplicación de lógica.

9. **Performance/Analytics · Medium** — recompute hace `delete()` + `bulk_create()` para rangos (DailyAgg/PMC).  
   - **Archivos**: `analytics/pmc_engine.py`  
   - **Impacto**: para atletas con historial largo y many updates, puede volverse costoso (IO + locks); requiere estrategia incremental más fina/particionamiento a futuro.

10. **Backend/API contract · Low/Medium** — algunos endpoints usan “errores 500 para requerimientos de paginación” (UX) o retornan `[]` en error para no romper frontend.  
   - **Archivos**: `core/views.py` (nested actividades devuelve 500 si no hay paginación), `analytics/views.py` (PMC devuelve `[]` en excepción)  
   - **Impacto**: dificulta observabilidad y debugging; oculta fallas reales en producción.

11. **Migrations/Operaciones · Low** — migraciones “vacías” y duplicidad de numeración (ej. `core/migrations/0049_*`).  
   - **Archivos**: `core/migrations/0049_auto_20260102_1615.py`, `core/migrations/0049_plantilla_versioning.py`, `analytics/migrations/0011_auto_20260102_1615.py`  
   - **Impacto**: ruido operacional y riesgo de conflictos en ramas/merge migrations; onboarding más frágil.

12. **Frontend/Calidad · Low** — bug/artefacto visible: función duplicada en `AthleteDetail` (probable error de merge).  
   - **Archivos**: `frontend/src/pages/AthleteDetail.jsx`  
   - **Impacto**: riesgo de crash/lint/test; deuda técnica y confianza reducida.

---

## 5. Risks & Future Pitfalls

### 5.1 Integridad de datos (corto/mediano plazo)

- **Corto**: crecimiento de `Actividad.datos_brutos` y `StravaWebhookEvent.payload_raw` (JSON) puede inflar DB rápido.  
  - **Riesgo**: costos/latencia, backups lentos, VACUUM más caro.
- **Mediano**: cambios de coach/tenant y re-linking de identidades pueden producir “historias partidas” si no hay reglas explícitas (re-asignación, ownership de actividad).  

### 5.2 Seguridad (corto plazo)

- Swagger/metadata público + sin throttling + tokens en localStorage (modo bearer) = **combinación peligrosa** si se expone a Internet.
- Cookie auth requiere disciplina: `SameSite`, `Secure`, `Domain`, `CSRF_TRUSTED_ORIGINS` y CORS correctos por entorno, o habrá fallas sutiles.

### 5.3 Escalabilidad (mediano/largo plazo)

- **Colas**: onboarding con backfill (N=200 por atleta) + updates frecuentes puede saturar `strava_ingest` y provocar latencia en “freshness” de analytics.
- **Recomputes**: `delete + bulk_create` desde `start_date` puede convertirse en O(historial) con atletas muy activos.  
  - Necesitarán: recompute por ventanas, upserts parciales, o particionado/rolling windows.
- **Consultas hot**: listados por coach (alumnos/actividades/alerts) requieren índices compuestos y paginación consistente para evitar full scans.

### 5.4 Complejidad/deuda técnica (mediano plazo)

- Doble mundo legacy + nuevo (servicios/flows) aumenta coste cognitivo y riesgo de regresiones.
- El frontend ya muestra señales de contrato cambiante (normalización de múltiples shapes).

---

## 6. Recommended PR Roadmap (propuesto)

> Roadmap orientado a PRs pequeños y verificables. No es “arreglar todo ya”, sino cerrar riesgos y preparar escala.

### PR0 — Hardening de seguridad + superficie pública (ABSOLUTA)

- **Objetivo**: reducir riesgo inmediato de exposición/abuso.
- **Alcance**:
  - hacer Swagger **privado** (staff-only o detrás de flag/env)
  - añadir throttling DRF (auth endpoints + analytics + coach endpoints) y/o reverse-proxy rate limiting
  - definir posture clara de auth: priorizar **cookie HttpOnly** y desincentivar localStorage en prod
  - revisar CORS/CSRF para cookie auth “real” por entorno
- **Riesgo si no se hace**: enumeración + abuso (DoS) + compromiso de sesión en modo bearer.
- **Dependencias**: ninguna (debe ir primero).

### PR1 — Multi-tenant institucionalizado (fail-closed en toda la API)

- **Objetivo**: que sea *imposible* introducir endpoints con fuga cross-tenant.
- **Alcance**:
  - checklist/guardrails (base classes, mixins, tests) para cualquier APIView nueva
  - revisar endpoints no-ViewSet (analytics/coach) y asegurar patrón consistente
  - fortalecer tests de privacidad (ampliar “deny cross-tenant” y “fail closed”)
- **Riesgo si no se hace**: una feature nueva puede reabrir fugas.
- **Dependencias**: PR0 recomendado primero.

### PR2 — Datos/DB: constraints + consistencia de ownership

- **Objetivo**: evitar datos ambiguos a escala.
- **Alcance**:
  - definir invariantes: `Alumno.entrenador` requerido en producción (o reglas de orphan)
  - regla `Actividad.usuario` vs `Alumno.entrenador` (constraint o validación)
  - revisar índices compuestos “top queries” (coach+fecha, alumno+fecha, status+fecha)
  - limpiar migraciones vacías / ordenar historia (sin tocar schema en esta fase; planificar)
- **Riesgo si no se hace**: corrupción lógica silenciosa, bugs difíciles de reproducir.
- **Dependencias**: PR1 ayuda (tests), pero puede ir paralelo.

### PR3 — Celery/Strava operable a gran escala (observabilidad + timeouts)

- **Objetivo**: que el pipeline sea operable con alta carga.
- **Alcance**:
  - time limits/soft time limits por task (strava + analytics)
  - políticas de reintento consistentes + DLQ/cola de fallos (según infra)
  - métricas/logging estructurado (event_uid, correlation_id) y dashboards (counts por status)
- **Riesgo si no se hace**: colas atascadas, pérdida de frescura, “black box” al fallar.
- **Dependencias**: PR0 (hardening), PR2 (datos) recomendado.

### PR4 — Analytics performance + contrato estable de métricas

- **Objetivo**: reducir costo de recompute y estabilizar definiciones de carga.
- **Alcance**:
  - consolidar “load canonical” como fuente única (y documentar versiones)
  - optimizar recompute incremental (evitar borrar todo si solo cambia 1 día)
  - estrategias de retención para raw payloads y caches (TTL/archivado)
- **Riesgo si no se hace**: costo creciente, inconsistencias en dashboards.
- **Dependencias**: PR3 recomendado antes.

### PR5 — Frontend: Coach Decisions/UX + estado de auth robusto

- **Objetivo**: UX consistente y menor fragilidad ante cambios de API.
- **Alcance**:
  - validar sesión (también en modo bearer) o migrar definitivamente a cookie auth
  - extraer “DTO normalizers” y fijar contrato (evitar múltiples keys)
  - introducir estrategia de data fetching (React Query/SWR) + states de error/loading uniformes
  - limpiar bugs de merge y mejorar tests (ya hay vitest)
- **Riesgo si no se hace**: deuda técnica y regresiones de UX con cambios backend.
- **Dependencias**: PR0 (auth posture) recomendado.

---

## 7. Quick Wins (bajo esfuerzo / alto impacto)

1. **Cerrar Swagger en prod** (flag/env + permiso staff-only).
2. **Agregar throttling DRF** (al menos para `/api/token/*`, `/webhooks/strava/`, `/api/coach/*`).
3. **Definir “modo prod”**: forzar `USE_COOKIE_AUTH=True` en producción y eliminar dependencia de localStorage.
4. **Reducir logging ruidoso** (ej. `urllib3 DEBUG`, `allauth DEBUG`) en prod; mantenerlo detrás de flag.
5. **Documentar invariantes de multi-tenant** y agregar checklist para nuevos endpoints.
6. **Retención de payloads**: política/TTL para `payload_raw`/`datos_brutos` (o al menos compresión/limpieza selectiva).
7. **Índices**: revisar queries top (alumno+fecha, entrenador+fecha) y confirmar compuestos donde haga falta.
8. **Contrato Coach Decisions**: documentar response shape y eliminar “normalización multi-formato” a futuro.
9. **Healthchecks**: consolidar `/healthz/*` como probes de infra y añadir “queue depth” si es viable.
10. **Auditoría de flags peligrosos**: `DISABLE_LEGACY_STRAVA_SYNC` (asegurar fail-closed en prod) + docs de operación.

---

## 8. Open Questions (para Fernando/CTO)

1. ¿Cuál es la prioridad real 2026: **Coach Decisions** (accionables) vs “analytics científicos” avanzados (cohortes/benchmarks)?
2. ¿Qué **SLA de frescura** esperan para el sync Strava (minutos vs horas) y para backfills?
3. ¿El “tenant” seguirá siendo **coach** o planean multi-tenant por “organización/gimnasio” (multi-coach por atleta)?
4. ¿Se quiere soportar **Garmin/Coros** a corto plazo o Strava seguirá siendo único proveedor?
5. ¿Volumen esperado de onboarding/backfills por semana (nuevos atletas) y tamaño típico de historial?
6. ¿Se requiere pronto billing/planes (impacta permisos, límites, aislamiento)?
7. ¿Requisitos legales para almacenar datos de salud (HR, VO2, etc.) y retención de datos?
8. ¿Cómo manejan “transferencia de atleta” entre coaches (ownership de actividades/plan histórico)?
9. ¿Necesitan un “audit log” de acciones del coach (ediciones de plan, cierres de alertas, etc.)?

---

## Appendix — Archivos clave inspeccionados (selección)

- Backend: `backend/settings.py`, `backend/urls.py`, `backend/celery.py`
- Core: `core/models.py`, `core/views.py`, `core/serializers.py`, `core/tasks.py`, `core/webhooks.py`, `core/services.py`
- Analytics: `analytics/models.py`, `analytics/tasks.py`, `analytics/pmc_engine.py`, `analytics/pmc.py`, `analytics/alerts.py`, `analytics/coach_views.py`
- Frontend: `frontend/src/api/client.js`, `frontend/src/context/AuthContext.jsx`, `frontend/src/components/CoachDecisionsPanel.jsx`, `frontend/src/pages/*`

