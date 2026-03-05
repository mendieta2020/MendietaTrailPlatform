# Strava Proof of Integration — Quantoryn

Strava is the only provider in production today. This document provides evidence of a
complete, hardened end-to-end integration.

## End-to-end flow

### Step 1 — Coach initiates connection for athlete

```
POST /api/integrations/strava/start
  Handler : core/integration_views.py — IntegrationStartView
  Action  : generate_oauth_state(provider="strava", user_id=coach_id, alumno_id=alumno_id)
            → HMAC-signed state with embedded nonce
            → Nonce stored in Redis with 15-minute TTL (core/oauth_state.py)
  Redirect: https://www.strava.com/oauth/authorize?client_id=...&state=<signed>
```

### Step 2 — Athlete authorises on Strava, Strava redirects back

```
GET /api/integrations/strava/callback?code=XXX&state=YYY
  Handler   : core/integration_callback_views.py — IntegrationCallbackView
  Validation:
    1. validate_and_consume_nonce(state) — core/oauth_state.py
       • Verify HMAC signature
       • Check timestamp: age >= 900s → reject (fail-closed)
       • Delete nonce from Redis (single-use)
    2. Tenant check: alumno.entrenador_id == payload["user_id"]
  Token     : Exchange code → access_token + refresh_token via Strava API
  Persist   : OAuthCredential.objects.update_or_create(alumno=alumno, provider="strava")
  Status    : OAuthIntegrationStatus.mark_connected(athlete_id=strava_athlete_id)
  Trigger   : drain_strava_events_for_athlete.delay(alumno_id)  ← background backfill
```

### Step 3 — Webhook subscription verification (Strava handshake)

```
GET /integrations/strava/webhook/?hub.mode=subscribe&hub.verify_token=XXX&hub.challenge=YYY
  Handler : core/webhooks.py — StravaWebhookView (also handles legacy core/webhooks.py)
  Security:
    • Resolves STRAVA_WEBHOOK_VERIFY_TOKEN at request time (never cached)
    • If setting not configured → HTTP 403 (fail-closed)
    • token == verify_token → return {"hub.challenge": YYY}
    • mismatch → HTTP 403
  Log     : strava_webhook_verify outcome=success|forbidden reason_code=...
```

### Step 4 — Strava delivers activity event

```
POST /integrations/strava/webhook/
  Handler : core/webhooks.py — StravaWebhookView
  Security:
    • CSRF-exempt (server-to-server callback)
    • AllowAny permission class
    • Rate throttle: StravaWebhookRateThrottle 120/min (core/throttling.py)
    • Subscription ID validated if STRAVA_WEBHOOK_SUBSCRIPTION_ID is set
  Action  :
    1. Parse event JSON (object_type, object_id, aspect_type, owner_id)
    2. StravaWebhookEvent.objects.get_or_create(strava_event_id=object_id)
       → duplicate events silently ignored (idempotent)
    3. Enqueue: process_strava_event.apply_async(queue="strava_ingest")
    4. Return HTTP 200 immediately
```

### Step 5 — Celery worker processes the event

```
core/tasks.py — process_strava_event
  1. Fetch activity detail from Strava API (using stored OAuthCredential)
  2. integrations/strava/mapper.py    — field mapping (Strava JSON → platform schema)
  3. integrations/strava/normalizer.py — unit / sport-type normalisation
  4. integrations/strava/elevation.py — elevation gain computation
  5. Actividad.objects.update_or_create(
         source="strava",
         source_object_id=str(strava_activity_id)
     )   ← idempotent (UniqueConstraint)
  6. Trigger analytics_recompute queue
```

### Step 6 — Analytics pipeline

```
analytics/pmc_engine.py     — CTL / ATL / TSB from canonical_load
analytics/plan_vs_actual.py — reconcile Actividad against Entrenamiento
analytics/injury_risk.py    — injury risk score
analytics/alerts.py         — coach notification if deviation detected
```

### Step 7 — Disconnect

```
POST /api/integrations/strava/disconnect/
  Handler : core/integration_views.py — IntegrationDisconnectView
  Action  :
    1. Revoke token at Strava API
    2. OAuthIntegrationStatus → DISCONNECTED
    3. OAuthCredential access_token + refresh_token zeroed / deleted
    4. ExternalIdentity.status → DISABLED
```

## Key models

| Model | File | Role |
|---|---|---|
| `OAuthCredential` | `core/models.py:784` | Stores Strava tokens per athlete |
| `OAuthIntegrationStatus` | `core/integration_models.py` | Connection state + error history |
| `ExternalIdentity` | `core/models.py:724` | Canonical Strava athlete id, pre-onboarding capable |
| `StravaWebhookEvent` | `core/models.py:522` | Webhook event ledger (idempotency layer 1) |
| `AthleteSyncState` | `core/models.py:472` | Per-athlete sync cursor |
| `Actividad` | `core/models.py:326` | Normalised activity (idempotency layer 2) |

## Test coverage

| Test file | Coverage |
|---|---|
| `core/tests_strava_webhook_verify.py` | Webhook handshake — valid/invalid token, missing config |
| `core/tests_pr1_webhooks.py` | Webhook event ingestion, idempotency |
| `core/tests_webhooks_reliability.py` | Retry logic, failed event handling |
| `core/tests_webhooks_missing_config.py` | Fail-closed when STRAVA_WEBHOOK_VERIFY_TOKEN not set |
| `core/tests_pr19_strava_state.py` | OAuth state/nonce generation and validation |
| `core/tests_oauth_callback.py` | Callback validation: expired state, tenant mismatch |
| `core/tests_oauth_credentials_bridge.py` | OAuthCredential upsert, uniqueness |
| `core/tests_oauth_integration.py` | Full integration flow |
| `core/tests_pr10_oauth_credential.py` | OAuthCredential model constraints |
| `core/tests_strava_diagnostics.py` | Diagnostics endpoint |

Total test suite: **338 tests, 0 failures** (as of PR-B merge).
