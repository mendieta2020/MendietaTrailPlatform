# Security and Compliance — Quantoryn

## Data storage

| Data type | Storage | Notes |
|---|---|---|
| Structured domain data | PostgreSQL (production) | `backend/settings.py:248` — env-driven, falls back to SQLite in dev/test |
| OAuth access + refresh tokens | PostgreSQL — `OAuthCredential` table | `core/models.py:784` — stored as `TextField`; never appear in logs |
| OAuth nonce / state | Redis (shared cache) | `core/oauth_state.py` — 15-minute TTL, single-use, fail-closed if Redis unavailable |
| Raw provider activity payloads | PostgreSQL JSON column (`datos_brutos` / `raw_payload`) | Retained for audit and re-processing; not transmitted externally |
| Session data | Django sessions (DB-backed or Redis) | Standard Django session framework |
| Static assets | WhiteNoise / Railway static volume | `whitenoise.middleware.WhiteNoiseMiddleware` |

**Retention policy**: TODO — formal data retention schedule to be defined. Suggested next PR:
`p1/data-retention-policy-and-deletion-api`.

## Token handling policy

### Storage
- Strava tokens managed via `django-allauth` social account adapter
  (`integrations/strava/oauth.py`).
- Future providers use `OAuthCredential` model: one row per `(alumno, provider)` pair,
  enforced by `UniqueConstraint` — `core/models.py:815`.
- `access_token` and `refresh_token` are stored as plain `TextField` in the database.
  TODO: evaluate field-level encryption (`django-encrypted-model-fields`) — suggested PR:
  `p1/encrypt-oauth-tokens-at-rest`.

### Rotation
- Token expiry tracked in `OAuthCredential.expires_at` and `OAuthIntegrationStatus.expires_at`.
- Refresh logic is provider-specific and lives in `integrations/<provider>/`.
- OAuth state nonce expires after 15 minutes (`OAUTH_NONCE_TTL_SECONDS = 900`); expired state
  is rejected fail-closed — `core/oauth_state.py:validate_and_consume_nonce`.

### What is logged (safe)
- OAuth event names: `oauth.state.malformed`, `oauth.nonce.consumed`, `oauth.callback.user_denied`
- Webhook events: `strava_webhook_verify outcome=success`, `strava_webhook_verify reason_code=token_mismatch`
- Structured fields: `provider`, `user_id`, `outcome`, `reason_code`, `age_seconds`

### What we do NOT log
- `access_token` — never appears in any log statement.
- `refresh_token` — never appears in any log statement.
- `client_secret` — never appears in any log statement.
- `hub.verify_token` — never logged; only compared at runtime.
- Raw OAuth authorization codes.

Evidence: `integrations/strava/oauth.py` `LoggedOAuth2Client.get_access_token` explicitly
sanitises before logging; `core/webhooks.py` logs `reason_code` only, not the token value.

## CSRF / CORS / ALLOWED_HOSTS

### CORS
```python
# backend/settings.py
CORS_ALLOW_ALL_ORIGINS = False   # hardcoded; never set True in any environment
CORS_ALLOW_CREDENTIALS = USE_COOKIE_AUTH
CORS_ALLOWED_ORIGINS = parse_env_list(env("CORS_ALLOWED_ORIGINS"))
```
Origins are whitelist-only, env-configured per deployment. `corsheaders.middleware.CorsMiddleware`
is the **first** item in `MIDDLEWARE` — `backend/settings.py:204`.

### CSRF
- Bearer JWT requests bypass CSRF via `core.middleware.BearerAuthCsrfBypassMiddleware`.
- Cookie-auth requests are protected by `django.middleware.csrf.CsrfViewMiddleware`.
- Strava webhook endpoint is `@csrf_exempt` (it is a server-to-server callback;
  authentication is via `hub.verify_token` comparison — `core/webhooks.py`).
- `CSRF_TRUSTED_ORIGINS` is env-configured for production; dev defaults to localhost only.

### ALLOWED_HOSTS
```python
# backend/settings.py:82
if DEBUG:
    ALLOWED_HOSTS = ['*']   # dev / ngrok tunnels only
else:
    ALLOWED_HOSTS = env("ALLOWED_HOSTS").split(",")
```
Production hosts are explicit; wildcard is debug-only.

## Tenant isolation — fail-closed

Every data row is scoped to a `coach` (User) acting as the organisation anchor:

- `Alumno.entrenador` — FK to `AUTH_USER_MODEL` (non-nullable for active athletes)
- `CompletedActivity.organization` — FK to `AUTH_USER_MODEL`, **non-nullable**
- `OAuthCredential.alumno` — scoped to athlete, athlete is scoped to coach
- `OAuthIntegrationStatus.alumno` — same chain

`core.middleware.TenantContextMiddleware` sets `request.tenant_coach_id` on every request.
All coach-facing viewsets inherit from `TenantModelViewSet` which injects the tenant filter
automatically — cross-tenant data cannot be read or written by any request that does not own
the tenant.

**Fail-closed**: if organisation scoping cannot be determined (missing auth), the request is
rejected with 401/403 — never falls back to global access.

## Rate limiting

Implemented in `core/throttling.py` using path-prefix scoping:

| Scope | Path prefix | Limit |
|---|---|---|
| `token` | `/api/token/` | 20 / min |
| `strava_webhook` | `/webhooks/strava/` | 120 / min |
| `coach` | `/api/coach/` | 600 / min |
| `analytics` | `/api/analytics/` | 600 / min |

Configured in `backend/settings.py:366` (`DEFAULT_THROTTLE_RATES`).

## Security contacts and incident process

**Security contact**: TODO — `security@yourdomain.com`
**Incident response SLA**: TODO — define P0 / P1 SLA document
**Suggested PR**: `p1/incident-response-runbook`
