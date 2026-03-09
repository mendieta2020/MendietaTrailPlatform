# Integration Architecture — Quantoryn

**Version**: 1.0
**Date**: 2026-03-05
**Contact**: partnerships@quantoryn.com

This document describes how Quantoryn connects to external activity providers, ingests athlete
data, and maintains clean separation between provider-specific concerns and coaching domain logic.

---

## Guiding design principles

### Provider isolation

All provider-specific code — OAuth flow, payload mapping, data normalisation — lives exclusively
inside a dedicated `integrations/<provider>/` module. The coaching domain layer has no direct
dependency on any provider's data format or API contract.

This means:

- Adding Garmin does not modify the activity storage layer.
- A Strava API change does not affect the COROS integration.
- Each provider integration is independently testable and deployable.

### Inbound-only / no data re-export

Data received from provider APIs flows one direction: into Quantoryn's coaching database.
It is never forwarded to another provider, aggregated across organizations, or transmitted
to any third party.

### Fail-closed by default

If a required configuration value is missing (webhook verification token, OAuth credentials,
Redis cache for nonce storage), the integration rejects the operation with an error rather
than falling back to an insecure default.

---

## Provider capability model

Each provider is registered with a capability set declaring what it supports:

| Capability | Description |
|---|---|
| `inbound_activities` | Can deliver completed activities to Quantoryn |
| `webhooks` | Supports push delivery of new activity events |
| `backfill` | Supports historical activity retrieval |
| `outbound_workouts` | Can receive structured workouts from Quantoryn (roadmap) |

Quantoryn only calls provider APIs for capabilities that the provider has declared.
Unknown or unsupported capability requests are rejected at the registry level, not at runtime.

**Current status**: Strava has `inbound_activities`, `webhooks`, and `backfill` enabled.
All other providers are registered in the capability registry but have no capabilities
enabled until an integration is live.

---

## Connection flow (OAuth 2.0)

```
1. Coach initiates connection for an athlete
   POST /api/integrations/{provider}/start

2. Platform generates HMAC-signed OAuth state
   - Contains: provider, coach ID, athlete ID, timestamp, single-use nonce
   - Nonce stored in shared Redis cache (15-minute TTL)
   - State signed with Django's cryptographic signer

3. Athlete is redirected to provider's authorisation page

4. Provider redirects back with authorisation code and state
   GET /api/integrations/{provider}/callback?code=XXX&state=YYY

5. Platform validates state
   - Verifies HMAC signature
   - Checks timestamp (expired if age ≥ 15 minutes)
   - Consumes and deletes nonce (single-use — replay is impossible)
   - Verifies athlete belongs to the coach's organization

6. Platform exchanges authorisation code for tokens
   POST to provider's token endpoint (server-side only)

7. Tokens stored per athlete-provider pair
   OAuthCredential: one row per (athlete, provider), enforced by database constraint

8. Integration status updated to CONNECTED
   OAuthIntegrationStatus: tracks connection state, expiry, and error history

9. Historical activity backfill triggered in background
```

---

## Inbound activity ingestion

### Webhook path (real-time)

```
Provider delivers POST to:
  /integrations/{provider}/webhook/

Platform responds:
  1. Verifies webhook signature / verification token
     → Rejects with 403 if verification token not configured (fail-closed)
  2. Acknowledges event immediately (HTTP 200)
     → Does not block on processing
  3. Persists event record for idempotency
     → Duplicate events from the same provider are silently ignored
  4. Enqueues processing task to background worker
```

```
Background worker:
  1. Fetches full activity detail from provider API
  2. Maps provider fields to platform schema (provider-specific mapper)
  3. Normalises units, sport types, elevation (provider-specific normaliser)
  4. Upserts activity record
     → Duplicate prevention via constraint on (provider, provider_activity_id)
  5. Triggers analytics recompute for the athlete
```

### Backfill path (historical)

Triggered automatically after OAuth connection completes and on coach request.
Uses the same normalisation pipeline as the webhook path.
Idempotency is enforced by the same database constraint — re-fetching an activity
that already exists produces no duplicate record.

---

## Inbound activity data

Quantoryn stores two representations of every activity:

**Normalised record** — provider-agnostic fields used by coaching analytics:

| Field | Description |
|---|---|
| `sport` | Mapped to Quantoryn's unified sport taxonomy |
| `start_time` | UTC timestamp |
| `duration_s` | Total duration in seconds |
| `distance_m` | Total distance in metres |
| `elevation_gain_m` | Cumulative ascent in metres |
| `provider` | Source provider identifier |
| `provider_activity_id` | Opaque provider-assigned ID (idempotency key) |
| `organization` | Owning coach organization (non-nullable, fail-closed) |

**Raw payload** — original provider JSON, stored verbatim for audit and re-processing.
Never transmitted outside the organization boundary.

---

## Plan vs Real separation

Quantoryn enforces a hard architectural boundary between planned and real data.

| Domain object | Represents |
|---|---|
| `Entrenamiento` | What the coach prescribed |
| `CompletedActivity` | What the athlete actually did (provider-sourced) |

These two objects are never merged. Reconciliation is an explicit, separately-triggered
operation that:

1. Attempts to match each completed activity to a planned session
2. Records a confidence score (0–1) and the matching algorithm version
3. Links the two objects via a nullable foreign key
4. Computes compliance percentage for the planned session

If a completed activity cannot be matched to any plan, it remains unreconciled.
Unreconciled activities are visible to the coach and counted in load analytics —
they do not disappear.

---

## Disconnect and revocation

```
POST /api/integrations/{provider}/disconnect/

Platform:
  1. Revokes OAuth tokens at provider
  2. Zeros stored credentials
  3. Sets integration status to DISCONNECTED
  4. Disables provider identity record
  5. Future webhook events for this athlete are ignored
```

Activities already imported are retained. Coach retains visibility of historical data.
Athlete can request full deletion via support@quantoryn.com (see `privacy-policy.md`).

---

## Idempotency guarantees

Two independent layers prevent duplicate data:

**Layer 1 — Webhook event deduplication**
Each incoming webhook event is stored before processing.
If the same event is delivered again (provider retry), the storage constraint rejects the
duplicate and no processing occurs.

**Layer 2 — Activity record deduplication**
The activity storage table has a database-level unique constraint on
`(organization, provider, provider_activity_id)`.
Re-ingesting the same activity from the same provider for the same organization is a no-op.

At-least-once delivery from any provider is therefore safe by design.

---

## Observability

Every integration event produces a structured log entry with the following fields:

| Field | Purpose |
|---|---|
| `event_name` | What happened (e.g. `oauth.nonce.consumed`, `webhook.received`) |
| `provider` | Which provider triggered the event |
| `outcome` | `success`, `error`, or `forbidden` |
| `reason_code` | Machine-readable reason (e.g. `token_mismatch`, `state_expired`) |
| `organization_id` | Owning coach organization |
| `user_id` | Authenticated user (never PII) |

Tokens, secrets, and raw payloads never appear in log output.

---

## Adding a new provider

To add Garmin, COROS, Polar, Suunto, or Wahoo:

1. Create `integrations/<provider>/` module
2. Implement OAuth adapter (connect, token exchange, refresh, revoke)
3. Implement activity mapper (provider fields → platform schema)
4. Implement normaliser (units, sport type, elevation)
5. Register provider capabilities in the capability registry
6. Add webhook handler if provider supports push delivery

No changes to domain models, analytics engine, or reconciliation logic are required.
