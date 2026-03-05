# Vendor Requirements Checklist — Quantoryn

Status legend: **DONE** ✅ | **PARTIAL** ⚠️ | **TODO** ❌

---

## Legal and policy

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Privacy Policy (public URL) | ❌ TODO | Not in repo. Needed: hosted page. PR: `p0/privacy-policy-page` |
| Terms of Service (public URL) | ❌ TODO | Not in repo. Needed: hosted page. PR: `p0/terms-of-service-page` |
| Legal entity name registered | ❌ TODO | Not in repo. Required for partnership agreements |
| DPA / data processing agreement template | ❌ TODO | Required by Garmin, Polar. PR: `p1/dpa-template` |
| License (open-source clarity) | ✅ DONE | MIT License — `LICENSE` (root) |

---

## Application security

| Requirement | Status | Evidence / Gap |
|---|---|---|
| HTTPS enforced in production | ⚠️ PARTIAL | Railway enforces TLS at edge. Django `SECURE_SSL_REDIRECT` not explicitly set — confirm in `backend/settings.py`. PR: `p1/enforce-secure-ssl-redirect` |
| CORS whitelist (no wildcard) | ✅ DONE | `CORS_ALLOW_ALL_ORIGINS = False` — `backend/settings.py` |
| CSRF protection | ✅ DONE | `CsrfViewMiddleware` + `BearerAuthCsrfBypassMiddleware` — `backend/settings.py:204` |
| Rate limiting on auth endpoints | ✅ DONE | `TokenEndpointRateThrottle` 20/min — `core/throttling.py` |
| Rate limiting on webhook endpoint | ✅ DONE | `StravaWebhookRateThrottle` 120/min — `core/throttling.py` |
| ALLOWED_HOSTS restricted in prod | ✅ DONE | Env-configured, wildcard only in DEBUG — `backend/settings.py:82` |
| Tokens never logged | ✅ DONE | `integrations/strava/oauth.py` sanitises; `core/oauth_state.py` logs only metadata |
| OAuth nonce / replay protection | ✅ DONE | Single-use Redis nonce, 15-min TTL — `core/oauth_state.py` |
| OAuth state HMAC-signed | ✅ DONE | `django.core.signing.Signer` — `core/oauth_state.py` |
| Token storage encryption at rest | ❌ TODO | Tokens stored as plain `TextField`. PR: `p1/encrypt-oauth-tokens-at-rest` |
| Dependency vulnerability scanning | ❌ TODO | No Dependabot / pip-audit in CI. PR: `p1/dependency-vulnerability-scan-ci` |

---

## OAuth / API integration

| Requirement | Status | Evidence / Gap |
|---|---|---|
| OAuth 2.0 PKCE or state anti-CSRF | ✅ DONE | State + nonce; PKCE available via `LoggedOAuth2Client` — `integrations/strava/oauth.py` |
| Token refresh implemented | ⚠️ PARTIAL | Tracked via `expires_at`; refresh flow in `integrations/strava/` but not yet fully automated for edge cases. PR: `p1/token-auto-refresh` |
| Disconnect / token revocation | ✅ DONE | `IntegrationDisconnectView` — `core/integration_views.py` |
| Webhook verification token | ✅ DONE | `STRAVA_WEBHOOK_VERIFY_TOKEN` fail-closed — `core/webhooks.py` |
| Idempotent webhook ingestion | ✅ DONE | `StravaWebhookEvent` unique + `Actividad` unique constraint — `core/models.py` |
| Backfill on connect | ✅ DONE | `drain_strava_events_for_athlete` — `core/tasks.py` |
| Provider payload isolated in integrations/ | ✅ DONE | All parsing in `integrations/strava/mapper.py` + `normalizer.py` |

---

## Data handling

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Multi-tenant data isolation | ✅ DONE | `TenantContextMiddleware` + FK scoping — `core/middleware.py`, `core/models.py` |
| Fail-closed on missing tenant | ✅ DONE | Non-nullable `organization` on `CompletedActivity`; viewsets reject unscoped queries |
| Raw payload retained for audit | ✅ DONE | `Actividad.datos_brutos` + `CompletedActivity.raw_payload` — `core/models.py` |
| Data retention policy defined | ❌ TODO | No formal policy. PR: `p1/data-retention-policy-and-deletion-api` |
| Athlete data deletion on request | ❌ TODO | No dedicated deletion API endpoint. PR: `p1/data-deletion-request-api` |
| Data minimisation (only necessary fields fetched) | ⚠️ PARTIAL | Raw payload stored; field-level minimisation not enforced. Acceptable for audit stage. |

---

## Operational

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Structured logs with event names | ✅ DONE | `event_name`, `provider`, `outcome`, `reason_code` in all integration logs |
| Security contact email | ❌ TODO | Needed for vendor forms. PR: `p0/security-contact-and-disclosure-policy` |
| Incident response process | ❌ TODO | No runbook. PR: `p1/incident-response-runbook` |
| Public status page | ❌ TODO | No status page. Nice-to-have for enterprise partnerships |
| Application deployed on managed cloud | ✅ DONE | Railway (`railway.toml`) with PostgreSQL + Redis |
| Background job processing | ✅ DONE | Celery with Redis broker — `backend/celery.py` |

---

## Summary counts

| Status | Count |
|---|---|
| ✅ DONE | 18 |
| ⚠️ PARTIAL | 4 |
| ❌ TODO | 11 |

Critical blockers for first vendor submission: Privacy Policy, Terms of Service, legal entity,
and security contact email.
