# Data Handling — Quantoryn

**Version**: 1.0
**Date**: 2026-03-05
**Contact**: support@quantoryn.com

This document describes how Quantoryn handles the data it receives from activity providers:
from the moment of OAuth token exchange through webhook ingestion, normalisation, storage,
and eventual deletion.

---

## 1. OAuth token lifecycle

### 1.1 Token acquisition

When a coach connects an athlete to an external provider:

1. An HMAC-signed state parameter is generated and stored as a single-use nonce in Redis
   (15-minute TTL).
2. The athlete is redirected to the provider's OAuth authorisation page.
3. Upon approval, the provider delivers an authorisation code to the platform callback URL.
4. The platform exchanges the code for access and refresh tokens — this exchange occurs
   server-side only. The code is never exposed to the browser after the redirect.
5. The state parameter is validated and the nonce is consumed (deleted from Redis).
   Replay of the same state is impossible.

### 1.2 Token storage

Tokens are stored in the PostgreSQL database, one row per (athlete, provider) pair.
A database-level unique constraint prevents duplicate credential records.

| Field | Stored | Notes |
|---|---|---|
| Access token | Yes | Database only; never in logs or cache |
| Refresh token | Yes | Database only; never in logs or cache |
| Token expiry | Yes | UTC timestamp; used to trigger refresh |
| External athlete ID | Yes | Provider-assigned opaque identifier |

**Tokens are never written to application logs under any circumstances.**

### 1.3 Token refresh

Token expiry is tracked. When an operation requires a valid token and the stored token
is expired or near expiry, a refresh is attempted using the stored refresh token.
Refresh logic is provider-specific and isolated to the provider's integration module.

If a refresh fails, the integration status is updated to `FAILED` with a reason code,
and the coach receives a visible prompt to reconnect. The platform does not silently
retry indefinitely.

### 1.4 Token revocation and deletion

When an athlete disconnects a provider integration:

1. Revocation is requested at the provider's token endpoint.
2. Stored access and refresh tokens are deleted from the database.
3. The integration status is set to `DISCONNECTED`.
4. The provider identity record is disabled.
5. Subsequent webhook events from that provider for that athlete are rejected.

---

## 2. Webhook ingestion

### 2.1 Receipt

Provider webhooks are received at a provider-specific endpoint:

```
POST /integrations/{provider}/webhook/
```

Upon receipt:

- The webhook verification token is validated (fail-closed: 403 if not configured).
- An event record is persisted to the database before any processing occurs.
  This guarantees that processing is retryable and that delivery is acknowledged
  immediately (providers typically require a response within 2 seconds).
- HTTP 200 is returned to the provider.
- The event is enqueued for background processing.

### 2.2 Processing

A background worker picks up the queued event and:

1. Fetches the full activity detail from the provider API using the athlete's stored token.
2. Passes the raw payload through the provider-specific mapper (field renaming).
3. Passes the mapped data through the provider-specific normaliser (unit conversion,
   sport type classification, elevation correction).
4. Upserts the normalised activity record. If a record with the same
   `(organization, provider, provider_activity_id)` already exists, the upsert is a no-op.
5. Triggers an analytics recompute for the athlete.

### 2.3 Idempotency

Duplicate webhook delivery is handled at two independent layers:

| Layer | Mechanism |
|---|---|
| Event receipt | Unique constraint on webhook event table; duplicate event IDs are rejected on insert |
| Activity storage | Unique constraint on `(organization, provider, provider_activity_id)`; re-ingesting the same activity is a no-op |

At-least-once delivery from any provider is safe. The platform processes each unique
activity exactly once regardless of how many times it is delivered.

### 2.4 Failure handling

If processing fails (provider API error, network timeout, data validation failure):

- The event record is marked `FAILED` with the error message and a timestamp.
- The failure is logged with structured fields (no payload content in logs).
- Retry is available on coach request. Automatic retry cadence is configurable.

---

## 3. Provider isolation

Each provider's integration is fully contained in a dedicated module:

```
integrations/
├── strava/
│   ├── mapper.py        Field mapping: Strava JSON → platform schema
│   ├── normalizer.py    Unit normalisation, sport type mapping, elevation
│   ├── elevation.py     Elevation gain computation
│   └── oauth.py         OAuth adapter (logged, credentials sanitised)
└── outbound/
    └── workout_delivery.py  Structured workout push (roadmap)
```

The coaching domain layer (`core/`) has no direct dependency on any provider module.
Provider modules import from core, but core never imports from provider modules.

This ensures:

- A bug or API change in the Strava module cannot affect a Garmin integration.
- Removing a provider is a matter of deleting its module and deregistering its capabilities.
- Each provider's data format is translated once, at the boundary, before entering the domain.

**Raw provider payloads are never passed into coaching analytics.** Analytics always
operate on normalised data. The raw payload is retained separately for audit.

---

## 4. Data classification

| Data class | Examples | Access scope |
|---|---|---|
| Athlete profile | Name, DOB, weight, physiological markers | Organisation only |
| Training plans | Sessions, intervals, zones, targets | Organisation only |
| Completed activities (normalised) | Sport, duration, distance, elevation, HR, power | Organisation only |
| Raw provider payloads | Original JSON from Strava / Garmin / etc. | Organisation only; not exposed via API |
| OAuth credentials | Access token, refresh token, expiry | Platform backend only; never in API responses |
| Webhook event log | Event ID, type, status, timestamps | Platform backend only |
| Application logs | Structured fields; no credentials or PII values | Platform operators only |

No data class is accessible across organisation boundaries.

---

## 5. Data retention philosophy

Quantoryn's retention approach follows these principles:

**Keep what is needed for coaching continuity.**
Activity history, load calculations, and plan compliance records are retained for
as long as the athlete is active within an organisation. Coaches need historical data
to understand long-term adaptation.

**Delete promptly on athlete removal.**
When an athlete record is deleted, all associated data — activities, credentials,
integration records, analytics snapshots — is deleted by database cascade.
No orphaned records remain.

**Preserve the audit trail within the retention window.**
Raw provider payloads are retained alongside normalised records so that any calculation
can be verified or reproduced against the original source data.

**Honour deletion requests unconditionally.**
Athlete or coach deletion requests are actioned within 30 days. See `privacy-policy.md`
for the full process.

| Data type | Retention | Deletion trigger |
|---|---|---|
| Completed activities | Duration of athlete membership | Athlete record deletion or explicit request |
| Raw provider payloads | Duration of athlete membership | Same |
| OAuth credentials | Until provider disconnected | Disconnect or athlete deletion |
| Webhook event log | 90 days (configurable) | Automated purge |
| Application logs | 30 days | Automated purge |
| Analytics snapshots | Duration of athlete membership | Athlete record deletion |

**Note**: A formal, per-field retention schedule with automated enforcement is in
development. The values above reflect current operational practice.

---

## 6. Security controls relevant to data handling

| Control | Status |
|---|---|
| HTTPS for all data in transit | Enforced at infrastructure level |
| Tokens never logged | Enforced — log sanitisation in OAuth adapter |
| Webhook endpoint verification (fail-closed) | Enforced — 403 if verification token not configured |
| OAuth nonce replay protection | Enforced — single-use nonce, Redis TTL |
| Multi-tenant query isolation | Enforced — database-level filter on every request |
| Token encryption at rest | Planned (`p1/encrypt-oauth-tokens-at-rest`) |

Full security documentation: `docs/compliance/security_policy.md`
