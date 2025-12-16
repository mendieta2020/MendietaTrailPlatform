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
python -m venv venv
# Windows
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
