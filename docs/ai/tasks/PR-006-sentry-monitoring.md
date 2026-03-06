# Task Capsule — PR-006: Sentry Error Monitoring

> **Phase:** P0 · **Risk:** Medium
> **Branch:** `p0/sentry-monitoring`
> **Scope:** Backend + Frontend — Sentry SDK initialization only

---

## Objective

Integrate Sentry error monitoring into both the Django backend and the React/Vite frontend. This gives the team real-time visibility into unhandled exceptions, failed requests, and worker task errors before and after launch — a P0 observability requirement. No business logic is changed.

Risk is **Medium** (not Low) because Sentry initialization wraps WSGI/ASGI and can interact with middleware ordering, and DSN secrets must be handled correctly.

---

## Classification

| Dimension | Value |
|-----------|-------|
| Phase | P0 |
| Risk | Medium |
| Blast radius | Settings init + main entry points only; no model/view/integration changes |
| Reversibility | High — SDK can be disabled via env var; no migrations involved |
| CI impact | Backend + frontend build checks; new env var required in CI secrets |

---

## Allowed Files (Allowlist)

Only these files may be modified in this PR:

```
# Backend
backend/config/settings/base.py
backend/config/settings/production.py
backend/config/wsgi.py          ← or asgi.py if used
requirements.txt                ← to add sentry-sdk

# Worker
worker/celery_app.py            ← or wherever Celery app is initialized
# (verify path before editing — do not guess)

# Frontend
frontend/src/main.jsx           ← or main.tsx; Sentry init goes here
frontend/package.json           ← to add @sentry/react
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to any view, model, serializer, or migration.
- No changes to `integrations/`.
- No changes to OAuth callback or webhook handler code.
- Do not add Sentry to individual view functions — SDK auto-instrumentation handles this.
- Do not log request bodies or user PII — Sentry must be configured to scrub sensitive data.
- Do not hardcode DSNs — use environment variables only.

---

## Blast Radius Notes

- **Tenancy risk: Low.** Sentry events are scoped to the Sentry project; no cross-org data leakage within the app. However, error messages must never contain tokens, raw payloads, or PII — enforce via `before_send` scrubber.
- **OAuth risk: Low.** Sentry wraps the WSGI layer but does not intercept request routing. Verify OAuth callbacks still work on a preview environment before merging.
- **Secrets risk: Medium.** The Sentry DSN is not a secret in the traditional sense (it is a public ingest URL), but it must still be set via environment variable — never hardcoded in source.
- **Worker risk: Low-Medium.** Celery integration initialization must not break task routing or beat schedule.
- **Performance:** Sentry adds minimal overhead. Set `traces_sample_rate` conservatively (e.g., `0.1` in production) to avoid trace volume explosion.

---

## Implementation Plan

### Step 1 — Add dependencies

**Backend:**
```
# requirements.txt
sentry-sdk[django,celery]==X.Y.Z   # pin to latest stable
```

**Frontend:**
```bash
npm install @sentry/react
```

Check the latest stable version before pinning. Do not use pre-release versions.

### Step 2 — Backend: initialize Sentry in `wsgi.py` (or `asgi.py`)

Sentry must be initialized **before** Django is fully loaded. The WSGI/ASGI entry point is the correct location.

```python
# backend/config/wsgi.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
import os

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,          # 10% of transactions traced
        send_default_pii=False,          # NEVER send PII
        before_send=_scrub_sensitive,    # see Step 3
        environment=os.environ.get("DJANGO_ENV", "production"),
    )
```

**Initialize only when `SENTRY_DSN` is present.** This ensures local and CI environments without the DSN are unaffected.

### Step 3 — Implement `before_send` scrubber

Add a `_scrub_sensitive` function before the `sentry_sdk.init()` call to strip sensitive fields from error payloads.

```python
def _scrub_sensitive(event, hint):
    """Remove tokens, secrets, and PII from Sentry events before sending."""
    sensitive_keys = {"access_token", "refresh_token", "password", "secret", "authorization"}
    request = event.get("request", {})
    headers = request.get("headers", {})
    for key in list(headers.keys()):
        if key.lower() in sensitive_keys:
            headers[key] = "[Filtered]"
    return event
```

### Step 4 — Worker: Celery integration

Add Celery integration in the Celery app initialization file.

```python
# worker/celery_app.py (verify exact path first)
from sentry_sdk.integrations.celery import CeleryIntegration

# Add CeleryIntegration() to the integrations list in the existing sentry_sdk.init() call
# OR initialize separately if backend and worker have separate entry points
```

Do not duplicate `sentry_sdk.init()` calls. If backend and worker share the same Django settings, one init call covers both.

### Step 5 — Frontend: initialize Sentry in `main.jsx`

```javascript
// frontend/src/main.jsx
import * as Sentry from "@sentry/react";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    // Do not enable session replay in P0 — it captures user input
  });
}
```

Add `VITE_SENTRY_DSN` to Vercel environment variables. **Never commit a real DSN to source.**

### Step 6 — Environment variable checklist

| Variable | Where set | Required in CI? |
|----------|-----------|-----------------|
| `SENTRY_DSN` | Railway env (backend/worker) | Optional — skip if not testing monitoring in CI |
| `VITE_SENTRY_DSN` | Vercel env (frontend) | Optional |
| `DJANGO_ENV` | Railway env | Yes (distinguishes staging vs prod) |

### Step 7 — Settings guard (production only for HTTPS-related Sentry config)

No Sentry-specific settings changes in `base.py` are required if DSN is handled via env var at the WSGI layer. Add only if Sentry recommends a Django settings integration point.

---

## Test Plan

```bash
# 1. Django system check
python manage.py check

# 2. Full backend test suite — confirm no import errors from sentry-sdk
python -m pytest -q

# 3. Frontend lint
cd frontend && npm run lint

# 4. Frontend build
cd frontend && npm run build

# 5. Manual smoke test (local or review environment)
# Trigger a deliberate error (e.g., divide by zero in a test view)
# Verify event appears in Sentry dashboard
# Verify no tokens appear in the Sentry event payload
```

### Protective test (minimal)

Add one test asserting that the `_scrub_sensitive` function removes known sensitive keys from a mock Sentry event. Place in `backend/core/tests_sentry.py` or equivalent.

```python
def test_scrub_sensitive_removes_tokens():
    event = {"request": {"headers": {"Authorization": "Bearer abc123", "Content-Type": "application/json"}}}
    result = _scrub_sensitive(event, hint={})
    assert result["request"]["headers"]["Authorization"] == "[Filtered]"
    assert result["request"]["headers"]["Content-Type"] == "application/json"
```

---

## Definition of Done

- [ ] `sentry-sdk[django,celery]` added to `requirements.txt` (pinned version)
- [ ] `@sentry/react` added to `frontend/package.json` (pinned version)
- [ ] Sentry initialized in `wsgi.py` (or `asgi.py`) — guarded by `if SENTRY_DSN`
- [ ] `before_send` scrubber implemented and tested
- [ ] Celery integration added to worker entry point
- [ ] Sentry initialized in `frontend/src/main.jsx` — guarded by `if VITE_SENTRY_DSN`
- [ ] No DSN hardcoded anywhere in source
- [ ] `send_default_pii=False` confirmed
- [ ] `python manage.py check` passes
- [ ] `python -m pytest -q` green (including scrubber test)
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] CI green on push
- [ ] Sentry DSN env vars documented in deployment runbook (Railway + Vercel)
- [ ] Manual smoke: real event visible in Sentry dashboard without PII

---

## Rollback Strategy

1. Remove `SENTRY_DSN` and `VITE_SENTRY_DSN` environment variables from Railway and Vercel.
2. Sentry initialization is guarded by `if SENTRY_DSN`, so removing the env var disables it instantly without a code deploy.
3. If a full removal is needed: revert `wsgi.py`, `main.jsx`, `requirements.txt`, and `package.json`; redeploy.
4. No migrations involved. No DB state affected.

---

*Capsule last updated: 2026-03-06 · See also: `docs/ai/CONSTITUTION.md`, `docs/ai/REPO_MAP.md`*
