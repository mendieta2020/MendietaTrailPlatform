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

- **Endpoint**: `POST /webhooks/strava/` (thin: responde 200 y encola)\n- **Handshake**: `GET /webhooks/strava/?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...`\n\n#### Simular webhook local

```bash
curl -s -X POST 'http://127.0.0.1:8000/webhooks/strava/' \\
  -H 'Content-Type: application/json' \\
  -d '{
    \"object_type\": \"activity\",
    \"aspect_type\": \"create\",
    \"object_id\": 1234567890,
    \"owner_id\": 111111,
    \"subscription_id\": 1,
    \"event_time\": 1700000000
  }' -i
```

#### Auditoría / estados (DB)

- **Idempotencia de eventos**: `core.StravaWebhookEvent` (unique `event_uid`, status, attempts, last_error)\n- **Logs de importación**: `core.StravaImportLog` (fetched/saved/discarded/failed)\n- **Dedupe de actividades**: `core.Actividad` unique `strava_id` + `validity/invalid_reason`\n- **Plan vs Actual**: `analytics.SessionComparison`\n- **Alertas**: `analytics.Alert`\n\nPara inspeccionar rápido en Django Admin: `http://127.0.0.1:8000/admin/` (requiere superuser).
