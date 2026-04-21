# MendietaTrailPlatform — Repository Map
> **Orientation layer for AI agents. Read this instead of scanning the entire repo.**
> Cross-reference with `docs/ai/CONSTITUTION.md` for governance rules.

---

## Top-Level Layout

```
MendietaTrailPlatform/
├── backend/          # Django / DRF API server
├── worker/           # Celery async worker (may share backend code)
├── frontend/         # React / Vite SPA
├── integrations/     # Provider-specific logic (Strava, etc.) — isolated boundary
├── docs/
│   └── ai/           # AI context layer (CONSTITUTION.md, REPO_MAP.md)
├── .github/          # CI workflows, issue templates
└── docker-compose / infra configs (Railway / Vercel)
```

---

## Backend — Django / DRF

| Area | Path pattern | Notes |
|------|-------------|-------|
| Project settings | `backend/config/settings/` | `base.py`, `production.py`, `local.py` — **sensitive zone** |
| URL routing | `backend/config/urls.py` | Root router; OAuth callback URLs live here |
| Core app | `backend/core/` | Domain models, views, serializers |
| Models | `backend/core/models.py` | `Organization`, `Membership`, `PlannedWorkout`, `CompletedActivity`, `ExternalIdentity`, `OAuthCredential`, `OAuthIntegrationStatus` |
| Views / API | `backend/core/views*.py` | DRF viewsets; always organization-scoped |
| OAuth views | `backend/core/views_oauth*.py` or similar | **Critical path** — Strava connect / callback / disconnect |
| Tests | `backend/core/tests*.py` | Unit + integration tests |
| Migrations | `backend/core/migrations/` | Touch only when explicitly requested |
| Authentication | allauth + custom session/cookie layer | **Sensitive zone** — do not weaken |

### Key Domain Models (organization-first)

| Model | Purpose |
|-------|---------|
| `Organization` | Tenant root — every record scopes to this |
| `Membership` | User ↔ Organization relationship; role-enforced |
| `PlannedWorkout` | Coach-authored plan — **never merge with real data** |
| `CompletedActivity` | Athlete-executed real data (inbound from Strava) |
| `ExternalIdentity` | Links a user to a provider account (Strava athlete ID) |
| `OAuthCredential` | Stores Strava access/refresh tokens (primary credential store) |
| `OAuthIntegrationStatus` | Per-org/user integration health state |

---

## Worker — Celery / Redis

| Area | Notes |
|------|-------|
| Task definitions | `worker/` or `backend/core/tasks.py` (verify path before editing) |
| Strava event processing | `strava.process_event` task — idempotency-critical |
| Broker | Redis (configured via `CELERY_BROKER_URL` in settings) |
| Idempotency | Every task must be safe to rerun; check for existing records before creating |
| **Sensitive zone** | Worker touches OAuth tokens and activity ingestion — high blast radius |

---

## Frontend — React / Vite

| Area | Path pattern | Notes |
|------|-------------|-------|
| App entry | `frontend/src/main.jsx` or `App.jsx` | Root component + routing |
| Pages / views | `frontend/src/pages/` | Route-level components |
| Components | `frontend/src/components/` | Reusable UI components |
| Connections UI | `frontend/src/components/Connections.jsx` (or similar) | Strava connect/disconnect — critical path adjacent |
| API client | `frontend/src/api/` or `frontend/src/services/` | All backend calls go through here |
| Auth state | React context or store — never store raw tokens in localStorage | **Sensitive zone** |
| Lint config | `frontend/.eslintrc.*` or `eslint.config.*` | Zero warnings policy |
| Build | Vite — `npm run dev` (local), `npm run build` (prod) |

---

## Integrations — Provider Boundary

```
integrations/
└── strava/
    ├── oauth.py        # Strava OAuth flow helpers
    ├── webhook.py      # Webhook payload parsing + dispatch
    ├── ingestion.py    # Activity data mapping → CompletedActivity
    └── ...
```

### Rules (Non-Negotiable)
- **All provider-specific logic lives exclusively in `integrations/`.**
- Domain models (`core/`) never import from `integrations/` provider modules.
- Integrations may call domain services but must not embed business rules.
- Any new provider follows the same `integrations/<provider>/` pattern.

---

## OAuth-Related Areas — High Caution

| Component | Location | Risk |
|-----------|----------|------|
| Strava OAuth initiation | `backend/core/views_oauth*.py` | High |
| Strava callback handler | `backend/core/views_oauth*.py` | **Critical** |
| Strava disconnect | `backend/core/views_oauth*.py` | High |
| Token storage | `OAuthCredential` model | High |
| Legacy token fallback | `allauth` `SocialToken` / `SocialAccount` | Backward-compat zone |
| Webhook endpoint | `integrations/strava/webhook.py` + URL config | **Critical** |
| OAuth state / nonce | Django cache (not DB) | Sensitive |

> ⚠️ **Never change callback URLs or webhook endpoint paths without a backward-compatibility plan and protective tests.**

---

## Tenancy Boundaries

- **Every database query must filter by `organization`.** No exceptions.
- `Membership` is the gate: a user's access to an organization's data is always checked via membership + role.
- Cross-organization data access = immediate fail condition.
- Settings, configs, and environment variables must never leak org-specific data.

### Checklist before touching any view or model
- [ ] Does the queryset filter by `organization`?
- [ ] Is the organization derived from the authenticated user's membership (not from request params)?
- [ ] Does the response serializer exclude fields from other organizations?

---

## Production Config / Settings — Sensitive Zone

| Setting | Location | Rule |
|---------|----------|------|
| `ALLOWED_HOSTS` | `settings/production.py` | Must be explicit; no wildcards |
| `CORS_ALLOWED_ORIGINS` | `settings/production.py` | Must be explicit |
| `CSRF_TRUSTED_ORIGINS` | `settings/production.py` | Must be explicit |
| `SESSION_COOKIE_SECURE` | `settings/production.py` | Must be `True` in prod |
| `SECRET_KEY` | Environment variable only | Never hardcode; never log |
| `STRAVA_CLIENT_ID/SECRET` | Environment variable only | Never hardcode; never log |
| `DATABASE_URL` | Environment variable only | Never hardcode; never log |
| Deploy targets | Railway (backend/worker), Vercel (frontend) | Check platform docs before infra changes |

---

## Tests and CI

| Area | Command | When to run |
|------|---------|-------------|
| Django system check | `python manage.py check` | Always before tests |
| Backend tests | `python -m pytest -q` | Always |
| Frontend lint | `npm run lint` | When frontend files are touched |
| Frontend build | `npm run build` | When validating frontend correctness |
| CI workflows | `.github/workflows/` | Automated on push/PR |

### Test file locations
- Backend: `backend/core/tests*.py` (e.g., `tests_oauth_callback.py`)
- Frontend: `frontend/src/**/*.test.*` (if present)

### CI Policy
- PR is not "Done" if any required CI check is red.
- Never skip or suppress a failing test; fix it or explicitly document why it is exempt.

---

## Sensitive Zones — Extra Care Required

| Zone | Why |
|------|-----|
| `backend/config/settings/` | Production security; secrets management |
| OAuth callback and disconnect views | Critical path; backward-compat contracts |
| `OAuthCredential` model and token lifecycle | Token security; provider backward compat |
| Webhook ingestion + idempotency logic | Data integrity; duplicate-event safety |
| `Membership` + organization scoping | Tenancy isolation |
| `allauth` `SocialToken` / `SocialAccount` | Legacy backward-compat layer |
| `frontend/` auth state management | Session/cookie security |
| `.github/workflows/` | CI pipeline integrity |

---

## What This Map Does NOT Cover

This map is intentionally high-level. It does **not** replace reading specific files when a task requires it. Use `CONSTITUTION.md` context budget rules when deciding which files to open.

For tasks outside this map's scope, **stop and ask** rather than exploring freely.

---

## Architecture Decision Records

Architectural decisions live in [`docs/decisions/`](../decisions/). Start there when you need to understand *why* a pattern exists.

- **Index:** [`docs/decisions/README.md`](../decisions/README.md)
- **Template:** [`docs/decisions/TEMPLATE.md`](../decisions/TEMPLATE.md) (MADR lite + `amended-by` / `partially-superseded-by`)
- **Workflow:** [`docs/decisions/HOWTO.md`](../decisions/HOWTO.md) (manual, no automation)

Current ADRs:

- [ADR-001 — Claude Design adoption deferred](../decisions/ADR-001-claude-design-deferred.md) (2026-04-21)
- [ADR-002 — Ratify teal as canonical Quantoryn brand](../decisions/ADR-002-teal-canonical-brand.md) (2026-04-21)

---

*Last updated: 2026-04-21 · See also: `docs/ai/CONSTITUTION.md`*
