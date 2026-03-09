# Vendor Readiness Summary — Quantoryn

This document summarizes Quantoryn's readiness across the key dimensions typically
evaluated in an API partnership or integration review.

---

## Legal and policy

| Requirement | Status |
|---|---|
| Privacy Policy (public URL) | Implemented — covers data sources, storage, token handling, deletion, and third-party sharing |
| Terms of Service (public URL) | Implemented — covers acceptable use, athlete data ownership, and liability |
| MIT License (open-source clarity) | Implemented |
| Legal entity registration | In progress |
| Data Processing Agreement (DPA) template | In progress |

---

## Application security

| Requirement | Status |
|---|---|
| HTTPS enforced in production | Implemented — TLS enforced at infrastructure and application level |
| CORS restricted to allowlist origins | Implemented — wildcard origins are never permitted |
| CSRF protection | Implemented — enforced for browser-authenticated sessions |
| Rate limiting on authentication endpoints | Implemented |
| Rate limiting on webhook endpoints | Implemented |
| Allowed host values restricted in production | Implemented |
| OAuth tokens never written to logs | Implemented |
| OAuth nonce / replay protection | Implemented — single-use nonce with TTL |
| OAuth state HMAC-signed | Implemented |
| Token storage encryption at rest | Planned — near-term improvement |
| Dependency vulnerability scanning in CI | Planned |

---

## OAuth / API integration

| Requirement | Status |
|---|---|
| OAuth 2.0 with state anti-CSRF | Implemented |
| Token refresh | Implemented — expiry tracked; refresh on demand |
| Disconnect / token revocation | Implemented — disconnect endpoint zeros credentials and disables integration |
| Webhook verification token (fail-closed) | Implemented — endpoint returns 403 if token not configured |
| Idempotent webhook ingestion | Implemented — duplicate events are silently ignored |
| Historical backfill on connect | Implemented |
| Provider payload isolated from domain layer | Implemented — all parsing in provider-specific modules |

---

## Data specification

| Requirement | Status |
|---|---|
| Data access justification documented | Implemented — see Data Access Specification |
| Per-sport data needs documented | Implemented — Running, Cycling, MTB, Strength |
| Stream access justification (why summary is insufficient) | Implemented — terrain-aware analytics require instantaneous correlation |
| Data minimization scope strategy | Implemented — Phase 1 minimized surface vs Phase 2 advanced |
| User control and revoke pathway | Implemented — disconnect endpoint; cascade delete; email deletion workflow |

---

## Data handling

| Requirement | Status |
|---|---|
| Multi-tenant data isolation | Implemented — database-level scoping on every request |
| Fail-closed on missing tenant context | Implemented — requests without valid organization context are rejected |
| Raw payload retained for audit | Implemented — original provider JSON stored separately from normalized records |
| Data retention policy | In progress — formal per-field schedule being finalized |
| Athlete data deletion on request | Implemented (verified support workflow, 30-day SLA); self-service endpoint planned |
| Data minimization enforcement | Documented in Data Access Specification; field-level enforcement in progress |

---

## Operational

| Requirement | Status |
|---|---|
| Structured logs with event names | Implemented — event name, provider, outcome, reason code on all integration events |
| Security contact email | Implemented — security@quantoryn.com; full disclosure policy at quantoryn.com/security |
| Incident response process | In progress — formal runbook being finalized |
| Application deployed on managed cloud | Implemented — Railway (PostgreSQL, Redis, background workers) |
| Background job processing | Implemented — Celery with Redis broker |
| Public status page | Planned |

---

## Summary

Quantoryn's core integration infrastructure — OAuth 2.0, webhook ingestion, multi-tenant
isolation, rate limiting, and data handling controls — is fully implemented and
production-verified through the Strava integration.

Items in progress (legal entity registration, DPA template, token encryption at rest,
formal retention schedule, and incident response runbook) are on the near-term roadmap
and do not represent gaps in current production security posture.

For questions about any item in this summary, contact **partnerships@quantoryn.com**.
