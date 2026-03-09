# Security Policy — Quantoryn

**Effective date**: 2026-03-05
**Last updated**: 2026-03-05
**Security contact**: security@quantoryn.com

---

## 1. Security contact

To report a security vulnerability or raise a security concern:

**Email**: security@quantoryn.com
**Subject line**: `[SECURITY] <brief description>`

We ask that you **do not** open a public GitHub issue for security vulnerabilities.

---

## 2. Vulnerability disclosure policy

Quantoryn follows a **coordinated responsible disclosure** model.

### 2.1 What to report

Please report any issue that could allow:

- Unauthorized access to data belonging to another coach organization (tenant boundary bypass).
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

We do not currently operate a bug bounty program, but we gratefully acknowledge
researchers who report valid findings.

---

## 3. Incident response

### Severity classification

| Severity | Description | Example |
|---|---|---|
| **Critical** | Data breach, cross-tenant access, token exposure | OAuth credential leaked |
| **High** | Auth bypass, privilege escalation | Unauthenticated access to coach endpoint |
| **Medium** | Information disclosure, partial auth bypass | Webhook without verify token accepted |
| **Low** | Non-sensitive information exposure | Stack trace in error response |

### Response steps

1. **Detect**: Alert from monitoring, security researcher report, or internal review.
2. **Contain**: Isolate affected service or credential; revoke tokens if exposed.
3. **Assess**: Determine scope — which tenants/athletes affected, what data accessed.
4. **Notify**: Inform affected coach organizations within 72 hours of confirmed breach
   (aligned with GDPR Article 33/34 requirements).
5. **Remediate**: Deploy fix; re-test; verify constraint holds in all environments.
6. **Post-mortem**: Document root cause, timeline, and preventive actions within 5 days.

---

## 4. Data protection principles

| Principle | Implementation |
|---|---|
| **Data minimization** | Only fields required for coaching analytics are stored; raw provider payload kept for audit only |
| **Purpose limitation** | Activity data used exclusively for coaching analytics — never for advertising or third-party sharing |
| **Storage security** | PostgreSQL with TLS in transit; Redis with TLS in transit; Railway-managed infrastructure |
| **Access control** | Token-based authentication; browser sessions use HttpOnly and SameSite cookie flags; CORS origin whitelist |
| **Audit trail** | Raw provider payload preserved for audit and future re-processing |
| **Token protection** | OAuth tokens never written to logs; stored in primary database; never in environment variables or browser storage |

---

## 5. Authentication and OAuth security

### 5.1 OAuth 2.0 implementation

- **State parameter**: HMAC-signed; includes a timestamp and a single-use nonce.
- **Nonce storage**: Cached with a 15-minute TTL; consumed (deleted) on first use.
  Replay attacks are rejected fail-closed.
- **Code exchange**: Performed server-side; authorization code never exposed to the browser
  after the redirect.
- **Token storage**: One credential record per athlete–provider pair; access and refresh
  tokens stored in the primary database.
- **Token logging**: Zero — all log output is sanitized before writing. OAuth tokens
  never appear in any log.

### 5.2 Webhook security

- Webhook endpoints validate a shared verification token at request time.
- If the verification token is not configured, the endpoint returns HTTP 403 (fail-closed).
- Webhook endpoints are rate-limited to prevent abuse.

### 5.3 Session and API security

- Authentication endpoints are rate-limited.
- CSRF protection is enforced for browser-authenticated sessions.
- API token (Bearer) requests use a separate authentication path that does not require
  browser session cookies.
- CORS origins are an explicit allowlist; wildcard origins are never permitted.
- Allowed host values are explicitly configured in production.

---

## 6. Tenant isolation model

Quantoryn is a multi-tenant platform. Tenant isolation is enforced at three layers:

| Layer | Mechanism |
|---|---|
| **Request** | Every authenticated request establishes the owning organization from the authenticated user's membership |
| **Query** | All data queries are automatically scoped to the authenticated organization |
| **Model** | Every data record carries a non-nullable reference to the owning organization |

**Fail-closed posture**: if the organization context cannot be determined from the
authenticated request, the response is HTTP 401/403. There is no fallback to global
data access.

---

## 7. Scope of this policy

This policy covers the Quantoryn web application and API, including:

- `https://quantoryn.com` and all subdomains.
- All API endpoints and integration endpoints.
- Infrastructure managed by Quantoryn on Railway (PostgreSQL, Redis, background workers).

**Out of scope**: Third-party provider APIs (Strava, etc.), Railway infrastructure
security, and athlete-owned devices.
