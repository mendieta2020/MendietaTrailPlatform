# Security Policy — Quantoryn

**Effective date**: 2026-03-05
**Last updated**: 2026-03-05
**Security contact**: security@quantoryn.com

---

## 1. Security contact

To report a security vulnerability or raise a security concern:

**Email**: security@quantoryn.com
**Subject line**: `[SECURITY] <brief description>`
**PGP key**: TODO — publish PGP public key at `/.well-known/security.txt`

We ask that you **do not** open a public GitHub issue for security vulnerabilities.

---

## 2. Vulnerability disclosure policy

Quantoryn follows a **coordinated responsible disclosure** model.

### 2.1 What to report

Please report any issue that could allow:

- Unauthorised access to data belonging to another coach organisation (tenant boundary bypass).
- Exposure of OAuth tokens, refresh tokens, or API credentials.
- Authentication bypass or privilege escalation.
- Remote code execution or server-side injection.
- Denial of service affecting other tenants.
- Webhook verification bypass.

### 2.2 What we ask of researchers

- **Do not** access, modify, or delete data that does not belong to you.
- **Do not** perform denial-of-service attacks.
- **Do not** attempt social engineering against Quantoryn staff.
- **Do not** disclose the vulnerability publicly until we have confirmed a fix is deployed
  or 90 days have elapsed from your initial report, whichever comes first.

### 2.3 What we commit to

| Commitment | Target |
|---|---|
| Initial acknowledgement | Within 48 hours of report |
| Triage and severity assessment | Within 5 business days |
| Fix deployment for Critical/High findings | Within 30 days |
| Fix deployment for Medium findings | Within 90 days |
| Credit to reporter (if desired) | On fix deployment |

We do not currently operate a bug bounty programme, but we gratefully acknowledge
researchers who report valid findings.

---

## 3. Incident response outline

### Severity classification

| Severity | Description | Example |
|---|---|---|
| **Critical** | Data breach, cross-tenant access, token exposure | OAuth credential leaked in logs |
| **High** | Auth bypass, privilege escalation | Unauthenticated access to coach endpoint |
| **Medium** | Information disclosure, partial auth bypass | Webhook without verify token accepted |
| **Low** | Non-sensitive information exposure | Stack trace in error response |

### Response steps

1. **Detect**: Alert from monitoring, security researcher report, or internal review.
2. **Contain**: Isolate affected service or credential; revoke tokens if exposed.
3. **Assess**: Determine scope — which tenants/athletes affected, what data accessed.
4. **Notify**: Inform affected coach organisations within 72 hours of confirmed breach
   (aligned with GDPR Article 33/34 requirements).
5. **Remediate**: Deploy fix; re-test; verify constraint holds in all environments.
6. **Post-mortem**: Document root cause, timeline, and preventive actions within 5 days.

**TODO**: Formal incident response runbook with escalation contacts —
`p1/incident-response-runbook`.

---

## 4. Data protection principles

| Principle | Implementation |
|---|---|
| **Data minimisation** | Only fields required for coaching analytics are stored; raw provider payload kept for audit only |
| **Purpose limitation** | Activity data used exclusively for coaching analytics — never for advertising or third-party sharing |
| **Storage security** | PostgreSQL with TLS in transit; Redis with TLS in transit; Railway-managed infrastructure |
| **Access control** | JWT-based authentication; cookie auth with HttpOnly + SameSite flags; CORS whitelist |
| **Audit trail** | Raw provider payload preserved in `datos_brutos` / `raw_payload` JSON columns |
| **Token protection** | OAuth tokens never written to logs; stored in database, never in environment logs or browser storage |

---

## 5. Authentication and OAuth security

### 5.1 OAuth 2.0 implementation

- **State parameter**: HMAC-signed via `django.core.signing.Signer`; includes a timestamp
  and a single-use nonce — `core/oauth_state.py`.
- **Nonce storage**: Redis shared cache with 15-minute TTL; consumed (deleted) on first use.
  Replay attacks are rejected fail-closed.
- **Code exchange**: Performed server-side; authorization code never exposed to the browser
  after the redirect.
- **Token storage**: `OAuthCredential` model — one row per (athlete, provider);
  access and refresh tokens stored in PostgreSQL.
- **Token logging**: Zero — the OAuth adapter (`integrations/strava/oauth.py`) explicitly
  sanitises log output before writing.

### 5.2 Webhook security

- Strava webhook endpoint (`/integrations/strava/webhook/`) validates
  `STRAVA_WEBHOOK_VERIFY_TOKEN` at request time.
- If the environment variable is not set, the endpoint returns HTTP 403 (fail-closed).
- Subscription ID is validated when `STRAVA_WEBHOOK_SUBSCRIPTION_ID` is configured.
- Rate-limited to 120 requests/minute via `StravaWebhookRateThrottle` — `core/throttling.py`.

### 5.3 Session and API security

- Bearer JWT: 20 requests/minute on `/api/token/` (`TokenEndpointRateThrottle`).
- CSRF: enforced for cookie-authenticated sessions via `CsrfViewMiddleware`.
  JWT (Bearer) requests bypass CSRF via `BearerAuthCsrfBypassMiddleware`.
- CORS: `CORS_ALLOW_ALL_ORIGINS = False`; origins are explicit whitelist only.
- ALLOWED_HOSTS: wildcard only in `DEBUG=True`; production is env-configured.

---

## 6. Tenant isolation model

Quantoryn is a multi-tenant platform. Tenant isolation is enforced at three layers:

| Layer | Mechanism |
|---|---|
| **Request** | `TenantContextMiddleware` sets `request.tenant_coach_id` on every authenticated request |
| **Query** | All coach-facing viewsets inherit from `TenantModelViewSet`, which injects tenant filter automatically |
| **Model** | Every data record carries a non-nullable FK to the owning coach organisation |

**Fail-closed posture**: if the tenant cannot be determined from the authenticated request,
the response is HTTP 401/403. There is no fallback to global data access.

The `CompletedActivity.organization` field is declared non-nullable — a row without an
organisation anchor cannot be inserted.

---

## 7. Known limitations and planned improvements

| Item | Status | Planned PR |
|---|---|---|
| OAuth token field-level encryption at rest | TODO | `p1/encrypt-oauth-tokens-at-rest` |
| Automated dependency vulnerability scanning | TODO | `p1/dependency-vulnerability-scan-ci` |
| `SECURE_SSL_REDIRECT` enforcement in Django | TODO | `p1/enforce-secure-ssl-redirect` |
| Formal incident response runbook | TODO | `p1/incident-response-runbook` |
| `security.txt` at `/.well-known/security.txt` | TODO | `p1/security-txt-well-known` |

We publish this list in the spirit of transparency. None of the above items represent an
active vulnerability, but we commit to addressing them in order of priority.

---

## 8. Scope of this policy

This policy covers the Quantoryn web application and API, including:

- `https://yourdomain.com` and all subdomains.
- All API endpoints under `/api/`, `/webhooks/`, and `/integrations/`.
- Infrastructure managed by Quantoryn on Railway (PostgreSQL, Redis, Celery workers).

**Out of scope**: Third-party provider APIs (Strava, Garmin, etc.), Railway infrastructure
security, and athlete-owned devices.
