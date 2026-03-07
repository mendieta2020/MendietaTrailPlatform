# Integration Architecture — Quantoryn

## Design principle

Provider-specific logic is **fully contained inside `integrations/<provider>/`**.
The domain layer (`core/`) speaks only in normalised platform types.
This means adding Garmin, COROS, or Polar requires zero changes to domain models, views, or
the reconciliation engine.

Capability contract defined in: `docs/ADR-001-capability-based-provider-design.md`
Registry: `core/providers.py`, `core/provider_capabilities.py`

## Provider lifecycle — end-to-end

### 1. Connect (OAuth 2.0)

```
Coach triggers connect for Athlete
  → POST /api/integrations/{provider}/start
  → IntegrationStartView (core/integration_views.py)
  → generate_oauth_state() → signs state + stores nonce in Redis
  → Redirect to provider authorisation URL

Provider redirects back
  → GET /api/integrations/{provider}/callback?code=XXX&state=YYY
  → IntegrationCallbackView (core/integration_callback_views.py)
  → validate_and_consume_nonce(state)  ← single-use, Redis-backed, fail-closed
  → Tenant check: alumno.entrenador == state.user_id
  → Exchange code → access_token + refresh_token
  → Upsert OAuthCredential (core/models.py:784)
  → Update OAuthIntegrationStatus → CONNECTED (core/integration_models.py)
  → Trigger background activity backfill
```

State security: `core/oauth_state.py` — HMAC-signed state, nonce TTL=15min,
timestamp expiry checked as `>= TTL` (fail-closed), single-use consumption via Redis `DELETE`.

### 2. Token lifecycle

- Expiry tracked in `OAuthCredential.expires_at` and `OAuthIntegrationStatus.expires_at`.
- Refresh logic lives exclusively in `integrations/<provider>/` — never in core.
- `OAuthIntegrationStatus` records error history: `error_reason`, `error_message`,
  `last_error_at` — enabling coach-visible "reconnect" prompts.

### 3. Webhook ingestion

```
Provider sends POST /integrations/strava/webhook/
  → StravaWebhookView (core/webhooks.py)
  → Verify hub.verify_token (fail-closed: 403 if setting not configured)
  → Validate subscription_id if STRAVA_WEBHOOK_SUBSCRIPTION_ID is set
  → Upsert StravaWebhookEvent (idempotent — duplicate events are dropped)
  → Enqueue Celery task: process_strava_event (queue: strava_ingest)
  → Return HTTP 200 immediately (Strava requires fast acknowledgement)

Celery worker picks up event
  → Fetch activity from Strava API
  → Map + normalise via integrations/strava/mapper.py + normalizer.py
  → Upsert Actividad (core/models.py:326)
  → Trigger analytics recompute (queue: analytics_recompute)
```

### 4. Backfill

Triggered post-connect and on-demand:
- `core/tasks.py: drain_strava_events_for_athlete`
- Fetches historical activities from provider API
- Same normalisation pipeline as live webhook path
- Idempotency enforced by same `UniqueConstraint` on `Actividad`

### 5. Normalisation

All provider payload parsing stays in `integrations/strava/`:

| File | Responsibility |
|---|---|
| `integrations/strava/mapper.py` | Map raw Strava JSON fields to platform field names |
| `integrations/strava/normalizer.py` | Normalise units, sport types, elevation |
| `integrations/strava/elevation.py` | Elevation gain computation and correction |
| `integrations/strava/oauth.py` | OAuth adapter (logged, sanitised) |

The domain model (`Actividad`) receives **only** normalised data. The raw provider payload is
preserved in `datos_brutos` (JSON column) for audit and future re-processing.

### 6. Plan vs Real reconciliation

See `data_model_plan_vs_real.md` for the full separation model.

Reconciliation metadata on `Actividad`:
- `reconciled_at` — timestamp of last reconciliation run
- `reconciliation_score` — float confidence 0–1
- `reconciliation_method` — string identifying the matching algorithm version
- `entrenamiento` FK — nullable; set only when a match is found

Analytics engine: `analytics/plan_vs_actual.py`

### 7. Disconnect

```
POST /api/integrations/{provider}/disconnect/
  → IntegrationDisconnectView (core/integration_views.py)
  → Revoke token at provider (integrations/<provider>/)
  → OAuthIntegrationStatus → DISCONNECTED
  → OAuthCredential deleted or zeroed
  → ExternalIdentity.status → DISABLED
```

TODO: formal data deletion request handler (athlete requests deletion of all activity data
imported from their provider account). Suggested PR: `p1/data-deletion-request-api`.

## Idempotency guarantees

Two independent idempotency layers:

1. **Webhook event deduplication**: `StravaWebhookEvent` has a unique index on the provider
   event id — duplicate webhook deliveries are silently ignored.
2. **Activity deduplication**: `Actividad` has `UniqueConstraint` on
   `(source, source_object_id)` (non-blank) — `core/models.py:460`.
   `CompletedActivity` has `UniqueConstraint` on
   `(organization, provider, provider_activity_id)` — `core/models.py` (PR-B).

Result: at-least-once delivery from any provider is safe; re-delivery never creates duplicates.

## Structured log fields

All integration log events carry:

| Field | Example |
|---|---|
| `event_name` | `strava_webhook_verify`, `oauth.nonce.consumed` |
| `provider` | `strava` |
| `outcome` | `success`, `forbidden`, `error` |
| `reason_code` | `token_mismatch`, `nonce_invalid_or_reused`, `state_expired` |
| `user_id` | Integer (never PII in structured field) |
| `organization_id` | Integer (coach / tenant id) |

Fields defined and used consistently across `core/webhooks.py`, `core/oauth_state.py`,
`core/integration_callback_views.py`.

## Celery task queues

| Queue | Purpose |
|---|---|
| `strava_ingest` | Process incoming Strava webhook events |
| `analytics_recompute` | Re-run PMC / injury risk after new activity |
| `notifications` | Coach alerts (deviations, milestones) |

Configuration: `backend/celery.py`, `backend/settings.py`.

---

## Provider Adapter Architecture

### Two-layer provider design

Provider integration is split across two distinct layers, each with a separate
responsibility:

```
core/providers/<provider>.py          — Registry / capability declaration layer
integrations/<provider>/provider.py   — Implementation / adapter layer
```

**Layer 1 — Registry (core/providers/)**

`IntegrationProvider` (ABC defined in `core/providers/base.py`) is the capability
contract. Every provider declares what it supports via `capabilities()` before any
implementation exists. The registry (`core/providers/registry.py`) auto-registers
all providers at import time. The frontend uses this layer to show "Connected",
"Coming Soon", and "Disabled" states without needing live implementations.

| File | Class | Purpose |
|---|---|---|
| `core/providers/strava.py` | `StravaProvider` | enabled=True, full capabilities declared |
| `core/providers/garmin.py` | `GarminProvider` | enabled=False, capabilities stub |
| `core/providers/coros.py` | `CorosProvider` | enabled=False, capabilities stub |
| `core/providers/suunto.py` | `SuuntoProvider` | enabled=False, capabilities stub |
| `core/providers/polar.py` | `PolarProvider` | enabled=False, capabilities stub |
| `core/providers/wahoo.py` | `WahooProvider` | enabled=False, capabilities stub |

**Layer 2 — Adapters (integrations/<provider>/)**

`ProviderAdapter` classes contain the actual implementation: OAuth flow,
API calls, activity mapping, token refresh. They are never imported from
`core/` — only from their provider-specific ingestion tasks.

| File | Class | Status |
|---|---|---|
| `integrations/strava/oauth.py` | `LoggedStravaOAuth2Adapter` | Production |
| `integrations/strava/mapper.py` | `normalize_strava_activity()` | Production |
| `integrations/strava/normalizer.py` | `normalize_strava_activity_payload()` | Production |
| `integrations/garmin/provider.py` | `GarminProviderAdapter` | Stub |
| `integrations/coros/provider.py` | `CorosProviderAdapter` | Stub |
| `integrations/suunto/provider.py` | `SuuntoProviderAdapter` | Stub |
| `integrations/polar/provider.py` | `PolarProviderAdapter` | Stub |
| `integrations/wahoo/provider.py` | `WahooProviderAdapter` | Stub |

### Provider data flow (per-provider)

```
OAuth callback
  → integrations/<provider>/provider.py:exchange_code_for_token()
  → core/models.py:OAuthCredential (upsert, provider-agnostic store)
  → core/models.py:ExternalIdentity (link athlete to provider identity)

New activity (webhook or poll)
  → integrations/<provider>/mapper.py (raw JSON → stable dict)
  → integrations/<provider>/normalizer.py (stable dict → NormalizedActivity TypedDict)
  → decide_activity_creation() (product rules: sport + distance filter)
  → core/models.py:Actividad.objects.update_or_create(source=PROVIDER, source_object_id=...)
  → analytics pipeline (DailyActivityAgg → PMCHistory → InjuryRiskSnapshot)
```

### Provider source enum

`Actividad.Source` and `CompletedActivity.Provider` are the single source of truth
for which providers can produce activity data. All values are lowercase slugs matching
`provider_id` in the registry:

| Value | Provider | Status |
|---|---|---|
| `strava` | Strava | Production |
| `garmin` | Garmin Connect | Schema-ready, adapter stub |
| `coros` | COROS | Schema-ready, adapter stub |
| `suunto` | Suunto | Schema-ready, adapter stub |
| `polar` | Polar Accesslink | Schema-ready, adapter stub |
| `wahoo` | Wahoo Cloud API | Schema-ready, adapter stub |
| `manual` | Manual entry | Production |
| `other` | Other | Production |

### Rules

1. **Provider logic stays in `integrations/`.** `core/` models and views never import
   from `integrations/<provider>/`. Data crosses the boundary as normalised Python dicts.
2. **Enable via registry, not by editing models.** To activate a new provider:
   set `enabled=True` in `core/providers/<provider>.py` and implement the adapter.
3. **Idempotency is not optional.** Every adapter must produce a stable `provider_activity_id`
   so `Actividad`'s `(source, source_object_id)` UniqueConstraint can deduplicate retries.
4. **Normalise to the business TypedDict.** Adapters must produce a dict compatible with
   `NormalizedStravaBusinessActivity` (or its future multi-provider equivalent) before
   handing off to the domain ingestion pipeline.
5. **Tokens never leave `integrations/`.** Token refresh logic lives exclusively in
   `integrations/<provider>/` and writes back only to `OAuthCredential`.
