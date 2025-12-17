# MendietaTrailPlatform

Plataforma SaaS para entrenamiento de deportes de resistencia (trail/running/ciclismo) con:
- Dashboard de atleta y entrenador
- Gestión de planes y calendario
- Métricas de rendimiento (carga, cumplimiento, tendencias)
- Integraciones (Strava/webhooks en progreso)

## Stack
- Backend: Django + Django REST Framework
- Frontend: React (Vite) + Tailwind
- DB: PostgreSQL (local/dev), SQLite solo si aplica localmente
- Asíncrono: Celery (si aplica)

## Estructura
- `backend/` configuración del proyecto Django
- `core/` app principal (dominio)
- `analytics/` métricas/engine de performance
- `frontend/` UI React

## Cómo correr (dev)

### Backend

```bash
python3 -m venv venv
# Windows
.\venv\Scripts\activate
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py runserver
```

### Celery + Redis (Strava Webhooks / tareas async)

```bash
# Redis (broker/backend)
redis-server

# Worker Celery (en otra terminal)
celery -A backend.celery.app worker -l info
```

### Webhook Strava (robusto: idempotencia + dedupe + auditoría)

- **Endpoint**: `POST /webhooks/strava/` (thin: responde 200 y encola)
- **Handshake**: `GET /webhooks/strava/?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...`

#### Simular webhook local

```bash
curl -s -X POST 'http://127.0.0.1:8000/webhooks/strava/' \
  -H 'Content-Type: application/json' \
  -d '{
    "object_type": "activity",
    "aspect_type": "create",
    "object_id": 1234567890,
    "owner_id": 111111,
    "subscription_id": 1,
    "event_time": 1700000000
  }' -i
```

#### Auditoría / estados (DB)

- **Idempotencia de eventos**: `core.StravaWebhookEvent` (unique `event_uid`, status, attempts, last_error)
- **Logs de importación**: `core.StravaImportLog` (fetched/saved/discarded/failed)
- **Dedupe de actividades**: `core.Actividad` unique `strava_id` + `validity/invalid_reason`
- **Plan vs Actual**: `analytics.SessionComparison`
- **Alertas**: `analytics.Alert`

Para inspeccionar rápido en Django Admin: `http://127.0.0.1:8000/admin/` (requiere superuser).

## Prueba de fuego (E2E): Frontend + JWT + Analytics Alerts (sin romper legacy)

### Requisitos
- **Backend** corriendo en `http://127.0.0.1:8000`
- **Frontend** (Vite) con base URL configurada:
  - `VITE_API_BASE_URL=http://127.0.0.1:8000` (preferida)
  - compat: también funciona `VITE_API_URL=...`

### Probar con curl (JWT real)

1) Obtener tokens:

```bash
curl -s -X POST 'http://127.0.0.1:8000/api/token/' \
  -H 'Content-Type: application/json' \
  -d '{"username":"<USER>","password":"<PASS>"}'
```

2) Llamar Alerts con paginación opt-in (envelope DRF):

```bash
ACCESS='<PEGAR_ACCESS>'
curl -s 'http://127.0.0.1:8000/api/analytics/alerts/?page=1&page_size=20' \
  -H "Authorization: Bearer ${ACCESS}"
```

3) Verificar compat legacy (sin page/page_size => **lista plana**):

```bash
ACCESS='<PEGAR_ACCESS>'
curl -s 'http://127.0.0.1:8000/api/analytics/alerts/' \
  -H "Authorization: Bearer ${ACCESS}"
```

4) Refresh token (cuando expira el access):

```bash
REFRESH='<PEGAR_REFRESH>'
curl -s -X POST 'http://127.0.0.1:8000/api/token/refresh/' \
  -H 'Content-Type: application/json' \
  -d "{\"refresh\":\"${REFRESH}\"}"
```

### Probar en UI (prueba de fuego)
- Abrí el frontend y logueate (pantalla `/`).
- Entrá a `/dashboard`.
- En el widget **“Alertas de rendimiento”** se hace:
  - `GET /api/analytics/alerts/?page=1&page_size=20` con `Authorization: Bearer <access>`
  - refresh automático si el backend responde `401` por access expirado
  - si falla el refresh: se limpian tokens y vuelve a login
