# Railway Operations Runbook

> Muscle memory, not poetry. Short, testable procedures for operations on
> MendietaTrailPlatform / Quantoryn infrastructure running on Railway.
>
> **Stale runbooks are worse than no runbook.** Dry-run all procedures every 90 days.

- Last reviewed: 2026-04-22
- Next scheduled dry-run: 2026-07-22
- Related: [ADR-003 — Railway env vars references](../decisions/ADR-003-railway-env-vars-references.md)

---

## Table of contents

1. Services map
2. Variable reference table
3. Rotate Postgres password
4. Rotate external API secrets
5. Audit procedure
6. Troubleshooting: `password authentication failed` after rotation
7. Troubleshooting: Celery tasks failing with DB errors
8. New service onboarding checklist
9. Incidents log

---

## 1. Services map

Railway project: `gregarious-celebration`, environment: `production`.

| Service | Role | Public? |
|---|---|---|
| `MendietaTrailPlatform` | Django backend (REST API) | Yes — `api.quantoryn.com` |
| `agile-alignment` | Celery worker (async tasks) | No — internal only |
| `Postgres` | Primary database | No — internal only |
| `Redis` | Celery broker + Django cache | No — internal only |

Frontend is hosted on Vercel (`app.quantoryn.com`), not covered by this runbook.

## 2. Variable reference table

### Backend (`MendietaTrailPlatform`)

| Variable | Expected value | Kind |
|---|---|---|
| `DB_HOST` | `${{Postgres.PGHOST}}` | reference |
| `DB_NAME` | `${{Postgres.PGDATABASE}}` | reference |
| `DB_PASSWORD` | `${{Postgres.PGPASSWORD}}` | reference |
| `DB_PORT` | `${{Postgres.PGPORT}}` | reference |
| `DB_USER` | `${{Postgres.PGUSER}}` | reference |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | reference |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | reference |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` | reference |
| `CELERY_RESULT_BACKEND` | `${{Redis.REDIS_URL}}` | reference |
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | (from Strava dev console) | static external |
| `MERCADOPAGO_ACCESS_TOKEN` / `MERCADOPAGO_CLIENT_ID` / `MERCADOPAGO_CLIENT_SECRET` / `MERCADOPAGO_PUBLIC_KEY` | (from MP panel) | static external |
| `MERCADOPAGO_WEBHOOK_SECRET` | (from MP panel, pending ticket WCS-36049) | static external |
| `RESEND_API_KEY` | (from Resend dashboard) | static external |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | (from Google Cloud Console) | static external |
| `OPENAI_API_KEY` | (from OpenAI dashboard) | static external |
| `SENTRY_DSN` | (from Sentry project settings) | static external |
| `SECRET_KEY` | (long random string) | static, rarely rotated |
| `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | explicit domain list | static config |
| `FRONTEND_URL` / `BACKEND_URL` / `PUBLIC_BASE_URL` | canonical URLs | static config |

### Worker (`agile-alignment`)

Same `DB_*`, `DATABASE_URL`, `REDIS_URL`, `CELERY_*` references as backend. Plus:

| Variable | Expected value | Kind |
|---|---|---|
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | (from Strava dev console) | static external |
| `STRAVA_REDIRECT_URI` | canonical callback URL | static config |
| `STRAVA_WEBHOOK_SUBSCRIPTION_ID` / `STRAVA_WEBHOOK_VERIFY_TOKEN` | (Strava webhook subscription) | static external |
| `OPENAI_API_KEY` | (from OpenAI dashboard) | static external |
| `SECRET_KEY` | same value as backend | static, must match |

## 3. Rotate Postgres password

**When to rotate**: every 90 days (security policy) or immediately if credentials may have leaked.

**Pre-check** (required):
1. Run the audit (section 5). Confirm 0 hardcoded `DB_*` variables across backend and worker.
2. Confirm no user-facing deploy is in progress.

**Steps**:
1. Railway → `Postgres` service → `Database` tab → `Regenerate password`.
2. Wait ~60 seconds. Railway automatically redeploys dependent services that use references.
3. Watch `agile-alignment` → `Deployments` → latest deploy logs. Must show no `psycopg2.OperationalError: password authentication failed`.
4. Watch `MendietaTrailPlatform` → latest deploy logs. Same check.
5. Smoke test: reconnect Strava on a test athlete (Natalia recommended). Worker log must show `Task strava.backfill_athlete[...] succeeded`.

**Expected duration**: 2–3 minutes including verification.

**Rollback**: if any service fails auth after rotation, go to section 6.

**Last successfully tested**: 2026-04-22 (Fernando, manual dry-run after refactor).

## 4. Rotate external API secrets

These secrets come from third-party providers and are NOT Railway references. Each has its own procedure.

| Secret | When to rotate | Procedure |
|---|---|---|
| `STRAVA_CLIENT_SECRET` | Only if leaked | Strava dev console → Your apps → regenerate client secret → update in Railway backend + worker → redeploy. Validate with reconnect flow. |
| `MERCADOPAGO_WEBHOOK_SECRET` | Pending ticket WCS-36049 resolution (MP support) | MP panel → Integrations → Webhooks → regenerate secret → add to Railway backend as `MERCADOPAGO_WEBHOOK_SECRET` → redeploy. Validate: POST a test webhook, confirm `mp.webhook.signature_verified` log (not `signature_check_skipped`). |
| `MERCADOPAGO_ACCESS_TOKEN` | If MP requires it | MP panel → credentials → copy new access token → update in Railway backend → redeploy. |
| `RESEND_API_KEY` | If leaked | Resend dashboard → API keys → create new → update in Railway backend → redeploy. Validate by triggering a password reset email. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | If leaked | Google Cloud Console → APIs & Services → Credentials → OAuth client → regenerate → update both in Railway backend. Test Google Sign-In. |
| `OPENAI_API_KEY` | If leaked | OpenAI dashboard → API keys → new key → update Railway backend + worker → redeploy. |
| `SECRET_KEY` (Django) | **Only if leaked — rotation invalidates all active sessions** | Generate new random string (`python -c "import secrets; print(secrets.token_urlsafe(50))"` offline on local machine) → update Railway backend + worker (must match across services) → redeploy. **Warn users in advance**: all logged-in sessions will require re-login. |
| `SENTRY_DSN` | If Sentry project changes | Sentry → project settings → new DSN → update Railway backend → redeploy. |

**Rule**: after rotating any external secret, always run the full smoke test for the affected integration before closing the task.

## 5. Audit procedure

**Goal**: confirm all internal-service variables in each Railway service use dynamic references.

**Steps**:
1. Railway → `MendietaTrailPlatform` → `Variables`.
2. For each variable in the table in section 2 marked as `reference`, click the value to reveal it. Confirm the value starts with `${{` and ends with `}}`.
3. If any internal-service variable is a raw string instead of a reference → immediately convert it (click the value, replace with the correct `${{...}}` syntax, save).
4. Repeat for `agile-alignment`.
5. Document the audit in the incidents log (section 9) if any variable was corrected.

**Cadence**: quarterly, on the same day as the Postgres rotation dry-run.

## 6. Troubleshooting: `password authentication failed` after rotation

**Symptom**: service logs show `psycopg2.OperationalError: FATAL: password authentication failed for user "postgres"` after a password rotation.

**Diagnosis**: at least one `DB_PASSWORD` (or `DATABASE_URL`) in the failing service is hardcoded instead of referencing `${{Postgres.PGPASSWORD}}`.

**Fix**:
1. Identify the failing service from Railway Deployments view.
2. Go to that service → `Variables`.
3. Find `DB_PASSWORD`. Click the value.
4. If the value is a raw string (not `${{Postgres.PGPASSWORD}}`), replace it with `${{Postgres.PGPASSWORD}}`.
5. Repeat for `DB_HOST`, `DB_USER`, `DB_NAME`, `DB_PORT`, `DATABASE_URL` if any are still hardcoded.
6. Save. Railway auto-redeploys.
7. Verify deploy logs no longer show the error.
8. Add entry to incidents log (section 9).

## 7. Troubleshooting: Celery tasks failing with DB errors

**Symptom**: worker (`agile-alignment`) logs show `Task X failed` with `django.db.utils.OperationalError` or `psycopg2.OperationalError`.

**Likely causes**:
- Same as section 6 — worker-side credentials out of sync.
- Postgres service itself is down (check Railway status).
- Connection pool exhaustion (check Postgres metrics; if connection count is near max, scale or restart).

**Fix for credentials case**: apply section 6 steps to `agile-alignment`.

## 8. New service onboarding checklist

When adding a new Railway service (e.g., staging backend, new worker, analytics service):

- [ ] Service created in same Railway project (`gregarious-celebration`) under `production` environment.
- [ ] All Postgres credentials use references: `DB_HOST`, `DB_NAME`, `DB_PASSWORD`, `DB_PORT`, `DB_USER`, `DATABASE_URL`.
- [ ] All Redis credentials use references: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
- [ ] External API secrets added as static values (from their respective dashboards).
- [ ] Variable reference table in section 2 updated with the new service's variables.
- [ ] Post-deploy smoke test documented and executed.
- [ ] Service added to services map in section 1.

## 9. Incidents log

Chronological record of infrastructure incidents and their resolutions.

| Date | Incident | Root cause | Fix | Outcome |
|---|---|---|---|---|
| 2026-04-21 | Backend `MendietaTrailPlatform` failed after Postgres password rotation | `DB_PASSWORD` hardcoded in backend variables | Converted `DB_PASSWORD` to `${{Postgres.PGPASSWORD}}` in Railway UI | Resolved same day; worker vars not checked at the time |
| 2026-04-22 | Worker `agile-alignment` failed with `psycopg2.OperationalError` on subsequent rotation; all async tasks (Strava backfill, MP webhook, PMC recompute) failed | Same root cause as 2026-04-21, but only backend was fixed; worker was still hardcoded | Converted DB + Redis + Celery vars in both services to references | Resolved; formalized in PR-181 (ADR-003 + this runbook) |
| 2026-04-22 | Validation dry-run: Postgres password rotated intentionally after full conversion | N/A — test | Confirmed zero downtime; backend and worker picked up new credentials automatically | Procedure section 3 validated |

**Format for new entries**: add one row per incident in chronological order. If a dry-run passes successfully without discovery, still add a row documenting the date and outcome so cadence is visible.
