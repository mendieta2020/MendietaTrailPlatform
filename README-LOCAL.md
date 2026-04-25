# Local Development Setup

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12 |
| Node.js | 20 |
| Docker + Docker Compose | Latest stable (Docker Desktop 4.x) |
| Git | Any recent version |

---

## .env.local (create this file at the repo root, never commit it)

```
DATABASE_URL=postgres://postgres:postgres@localhost:5432/mtp_local
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
DJANGO_DEBUG=True
DEBUG=True
SECRET_KEY=local-dev-secret-key-not-for-production
STRAVA_CLIENT_ID=<your-strava-dev-app-id>
STRAVA_CLIENT_SECRET=<your-strava-dev-app-secret>
OWM_API_KEY=<same-as-production-read-only>
FRONTEND_URL=http://localhost:5173
```

---

## Daily Commands

```bash
# Terminal 1 — services
docker-compose up -d

# Terminal 1 — backend bootstrap (first time or after migrations)
python manage.py migrate
python manage.py seed_test_users

# Terminal 1 — backend server
python manage.py runserver 8000

# Terminal 2 — Celery worker
celery -A backend worker -l info

# Terminal 3 — frontend
cd frontend && npm install && npm run dev
```

---

## Test Users

| Email | Password | Role |
|-------|----------|------|
| owner@test.com | test1234 | owner (superuser) |
| coach@test.com | test1234 | coach |
| atleta1@test.com | test1234 | athlete |
| atleta2@test.com | test1234 | athlete |

`seed_test_users` is idempotent — safe to run multiple times. Refuses to run when `DEBUG=False`.

---

## What Works Locally vs Not

| Feature | Status |
|---------|--------|
| Login / JWT session | ✅ |
| Calendar timeline (all views) | ✅ |
| Coach plan → athlete calendar | ✅ |
| Marcar completado + RPE capture | ✅ |
| Compliance calculation | ✅ |
| Notifications + navigation | ✅ |
| Strava webhook | ❌ Needs public URL — use ngrok |
| Strava OAuth callback | ❌ Needs registered redirect URI in Strava app |
| MercadoPago webhook | ❌ Same as Strava — needs public URL |

---

## Troubleshooting

**Port 8000 already in use**
Find and kill the process: `lsof -i :8000` (macOS/Linux) or `netstat -ano | findstr :8000` (Windows), then kill the PID.

**Redis not running**
Celery and some cache operations will fail silently. Run `docker-compose up -d redis` and verify with `docker ps`.

**Migration drift** (`django.db.utils.OperationalError: no such table`)
Run `python manage.py migrate`. If that fails with conflicts, run `python manage.py migrate --run-syncdb` as a last resort on local only.

**`seed_test_users` raises CommandError**
Ensure `DEBUG=True` is set in your environment. Check that your `.env.local` is loaded (some setups require `python-dotenv` or manual `export`).
