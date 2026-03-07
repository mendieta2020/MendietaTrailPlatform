# Vendor Integration Playbook — Quantoryn

> **Type:** Engineering playbook
> **Audience:** Developers, AI agents implementing new provider integrations
> **Architecture reference:** [`docs/vendor/integration_architecture.md`](../../vendor/integration_architecture.md)
> **Domain reference:** [`docs/domain/DOMAIN_MODEL.md`](../../domain/DOMAIN_MODEL.md)
> **Last updated:** 2026-03-07

This playbook is the step-by-step guide for adding a new provider to Quantoryn. Follow each stage in order. Do not skip stages. Do not merge a provider integration that has not completed all stages.

---

## The Two-Layer Provider Design

Every provider in Quantoryn is implemented across two layers. Understand this before writing any code.

```
Layer 1 — Registry / Capability
  core/providers/<provider>.py
  └── IntegrationProvider subclass
      Declares: enabled, capabilities, token refresh contract
      Does NOT: handle OAuth flows, parse payloads, normalize data

Layer 2 — Implementation Adapter
  integrations/<provider>/provider.py
  └── <Provider>ProviderAdapter class
      Handles: OAuth authorize URL, token exchange, token refresh,
               activity fetch, webhook receipt, payload normalization
      Does NOT: touch domain models directly — calls normalizer
```

**Law:** Provider-specific logic (OAuth secrets, payload parsing, normalization) lives **only** in `integrations/<provider>/`. Domain code (`core/`, `analytics/`) is provider-agnostic. Violating this boundary is a CI-blocking error.

---

## Stage 0 — Vendor Contact and API Access

Before writing any code:

1. **Obtain API credentials** — client ID, client secret, sandbox/test account.
2. **Read the vendor API documentation** and record:
   - OAuth version (2.0 or 1.0a — Garmin uses 1.0a, all others use 2.0)
   - Activity endpoint structure (pull vs. push/webhook)
   - Rate limits and quotas
   - Token lifetime and refresh mechanics
   - Webhook delivery guarantees (at-least-once vs. exactly-once)
   - Sandbox vs. production environment differences
3. **Verify webhook delivery** — Quantoryn's architecture expects `(organization, provider, provider_activity_id)` to be the deduplication key. Confirm the vendor provides a stable, unique activity ID.
4. **Document findings** in `integrations/<provider>/README.md` before implementation begins.

---

## Stage 1 — Scaffold the Provider Directory

Create the provider directory structure. Reference: `integrations/strava/` as the canonical example.

**Files to create:**

```
integrations/<provider>/
  __init__.py           — module marker; include OAuth version note if non-standard
  provider.py           — ProviderAdapter class (see template below)
  normalizer.py         — payload normalization (created in Stage 4)
  README.md             — status, credentials, implementation checklist
```

**`provider.py` template:**

```python
"""
integrations/<provider>/provider.py

Provider adapter for <Provider>.

OAuth version: 2.0 (or 1.0a — document if non-standard)
Activity delivery: webhook push / pull polling (choose one)

Provider boundary law:
All <Provider>-specific logic lives in this file and its siblings.
Domain code must never import from this module directly.
Use core/providers/registry.py to resolve providers by string slug.
"""
from __future__ import annotations

PROVIDER_ID = "<provider>"


class <Provider>ProviderAdapter:
    """
    Implementation adapter for <Provider>.
    Conforms to the two-layer provider contract.
    See: docs/vendor/integration_architecture.md
    """

    provider_id = PROVIDER_ID

    # --- OAuth ---

    def get_oauth_authorize_url(self, *, redirect_uri: str, state: str) -> str:
        raise NotImplementedError

    def exchange_code_for_token(self, *, code: str, redirect_uri: str) -> dict:
        """Returns dict with access_token, refresh_token, expires_at."""
        raise NotImplementedError

    def refresh_token(self, *, refresh_token: str) -> dict:
        """Returns dict with new access_token, refresh_token, expires_at."""
        raise NotImplementedError

    # --- Activity fetch ---

    def fetch_activities(
        self,
        *,
        access_token: str,
        after: int | None = None,
        before: int | None = None,
    ) -> list[dict]:
        """Returns list of raw provider activity dicts."""
        raise NotImplementedError

    # --- Normalization ---

    def normalize_activity(self, raw: dict) -> dict:
        """
        Delegates to integrations/<provider>/normalizer.py.
        Returns a provider-agnostic normalized dict ready for CompletedActivity.
        """
        from . import normalizer
        return normalizer.normalize(raw)
```

**Registry registration** — add the provider to `core/providers/<provider>.py`:

```python
# core/providers/<provider>.py
from .base import IntegrationProvider

class <Provider>Provider(IntegrationProvider):
    provider_id = "<provider>"
    enabled = False  # set True only when implementation is complete

    def capabilities(self):
        return {"oauth": True, "webhook": False, "pull": True}

    def refresh_token(self, credential):
        raise NotImplementedError
```

Register in `core/providers/registry.py` under the existing `_register_all()` call.

Add `"<provider>"` to `SUPPORTED_PROVIDERS` in `core/providers.py`.

---

## Stage 2 — OAuth Implementation

OAuth is the authentication foundation. It must be implemented and tested before any activity data can be fetched.

**Files to create/modify (within `integrations/<provider>/`):**

```
integrations/<provider>/oauth.py   — OAuth flow implementation
```

**Required functions:**

```python
def oauth2_login(request):
    """
    Redirects the user to the provider's authorization page.
    Stores state in session. Records OAuthIntegrationStatus = PENDING.
    """

def oauth2_callback(request):
    """
    Handles the provider redirect after user authorization.
    Exchanges code for tokens. Saves OAuthCredential.
    Creates or updates ExternalIdentity.
    Sets OAuthIntegrationStatus = CONNECTED.
    On error: sets OAuthIntegrationStatus = ERROR, logs structured event.
    """
```

**OAuthCredential storage rules:**
- Tokens are stored exclusively in `OAuthCredential` (core model).
- Tokens are NEVER logged. `_scrub_sensitive` before_send is active in Sentry.
- `OAuthCredential.expires_at` must be stored as UTC datetime.
- Refresh is triggered when `expires_at - now < 5 minutes`.

**Structured log fields for OAuth events** (required for observability):

```python
logger.info("oauth.connected", extra={
    "provider": PROVIDER_ID,
    "organization_id": str(org.id),
    "external_user_id": "<provider_user_id>",
    "event": "oauth.connected",
})
```

**ExternalIdentity:** Create with `linked=False` on first webhook receipt (before OAuth). Set `linked=True` after OAuth completes and identity is confirmed.

---

## Stage 3 — Webhook Ingestion (if provider supports push delivery)

Webhook ingestion is the real-time path. If the provider only supports pull polling, skip to Stage 4.

**Files to create/modify:**

```
integrations/<provider>/webhooks.py   — webhook view + event handler
core/urls.py                          — register webhook endpoint (allowlist approval required)
```

**Webhook view requirements:**

1. **Verify signature** — every provider signs webhook payloads. Verify before processing. Reject unsigned payloads with HTTP 400. Never process unverified webhooks.
2. **Acknowledge immediately** — return HTTP 200 within the request cycle. Hand off processing to Celery.
3. **Deduplicate** — use `(organization, provider, provider_activity_id)` as the unique key. `CompletedActivity.objects.get_or_create()` with this triple is the deduplication gate.
4. **Record raw payload** — store the original provider payload in `CompletedActivity.raw_payload` before normalization. This enables re-processing without re-fetching.

**Celery task pattern:**

```python
# integrations/<provider>/tasks.py

@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    queue="integrations",
)
def ingest_<provider>_activity(self, *, organization_id: int, raw_payload: dict):
    """
    Idempotent ingestion task.
    Safe to retry: get_or_create on (organization, provider, provider_activity_id).
    """
    try:
        _do_ingest(organization_id=organization_id, raw_payload=raw_payload)
    except Exception as exc:
        raise self.retry(exc=exc)
```

**Idempotency guarantee:** The `(organization, provider, provider_activity_id)` UniqueConstraint on `CompletedActivity` is the database-level deduplication guarantee. The Celery task is safe to retry because `get_or_create` is idempotent.

---

## Stage 4 — Activity Normalization

Normalization is the provider boundary in code. Raw provider payloads are translated into the Quantoryn `CompletedActivity` schema here and nowhere else.

**File to create:**

```
integrations/<provider>/normalizer.py
```

**Normalization contract:**

```python
# integrations/<provider>/normalizer.py

from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedActivity:
    """
    Provider-agnostic activity representation.
    All fields are in SI units (seconds, meters, watts, bpm).
    This is the only output the domain layer accepts.
    """
    provider: str                       # = PROVIDER_ID
    provider_activity_id: str
    sport: str                          # canonical sport slug
    started_at: str                     # ISO 8601 UTC
    duration_s: int
    distance_m: float
    elevation_gain_m: Optional[float]
    elevation_loss_m: Optional[float]
    avg_hr_bpm: Optional[int]
    max_hr_bpm: Optional[int]
    avg_power_watts: Optional[int]
    normalized_power_watts: Optional[int]
    tss: Optional[float]
    calories_kcal: Optional[float]
    source_hash: str                    # SHA-256 of key fields


def normalize(raw: dict) -> NormalizedActivity:
    """
    Translate a raw <Provider> activity payload to NormalizedActivity.

    Rules:
    - All units must be converted to SI (meters, seconds, watts, bpm).
    - Missing optional fields must be None, not zero.
    - sport must map to one of the canonical sport slugs.
    - source_hash must be computed from stable fields (see compute_source_hash).
    - This function must not make network calls.
    - This function must not access Django models.
    """
    raise NotImplementedError


def compute_source_hash(activity_id: str, started_at: str, duration_s: int) -> str:
    """SHA-256 of stable fields — used for change detection on re-ingestion."""
    import hashlib
    raw = f"{activity_id}:{started_at}:{duration_s}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

**Sport slug mapping** — map provider sport types to Quantoryn canonical values:

| Quantoryn slug | Description |
|---|---|
| `run` | Road running |
| `trail` | Trail running |
| `bike` | Cycling (road, gravel, MTB) |
| `strength` | Strength training |
| `mobility` | Mobility / stretching |
| `swim` | Swimming |
| `other` | All unrecognized types |

---

## Stage 5 — CompletedActivity Storage

After normalization, the `NormalizedActivity` is persisted to `CompletedActivity`. This stage does not live in `integrations/<provider>/` — it is handled by the shared ingestion service in `core/`.

**The ingestion service (existing):**

```python
# core/services_ingestion.py (future PR)

def ingest_normalized_activity(
    *,
    organization,
    normalized: NormalizedActivity,
    raw_payload: dict,
) -> tuple[CompletedActivity, bool]:
    """
    Idempotent: returns (activity, created).
    created=False means duplicate — caller should skip downstream processing.
    """
    activity, created = CompletedActivity.objects.get_or_create(
        organization=organization,
        provider=normalized.provider,
        provider_activity_id=normalized.provider_activity_id,
        defaults={
            "sport": normalized.sport,
            "started_at": normalized.started_at,
            "duration_s": normalized.duration_s,
            # ... all normalized fields
            "raw_payload": raw_payload,
            "source_hash": normalized.source_hash,
        },
    )
    return activity, created
```

**Plan ≠ Real law:** The ingestion service must never link `CompletedActivity` to a `PlannedWorkout`. That linkage is established later by `PlanRealCompare` (a separate, explicitly scoped reconciliation engine).

---

## Stage 6 — ActivityStream Ingestion (optional)

If the provider delivers time-series data (HR, power, GPS), ingest it into `ActivityStream`.

```python
# After CompletedActivity is created:

ActivityStream.objects.get_or_create(
    activity=activity,
    stream_type=ActivityStream.StreamType.HEARTRATE,
    defaults={"data": hr_samples, "resolution_s": 1.0},
)
```

Only ingest streams that are actually present in the provider payload. Do not create empty stream records.

---

## Stage 7 — Token Refresh

Token refresh must be implemented before the integration can operate in production. Stale tokens cause silent data gaps.

**Refresh trigger:** When `OAuthCredential.expires_at - now < 5 minutes`.

**Implementation:**

```python
# integrations/<provider>/provider.py

def refresh_token(self, *, refresh_token: str) -> dict:
    """
    Call provider token refresh endpoint.
    Returns: {"access_token": str, "refresh_token": str, "expires_at": datetime}
    On failure: raise ProviderTokenExpiredError (triggers OAuthIntegrationStatus = ERROR)
    """
    raise NotImplementedError
```

**Structured log on refresh failure:**

```python
logger.error("oauth.refresh_failed", extra={
    "provider": PROVIDER_ID,
    "organization_id": str(org.id),
    "event": "oauth.refresh_failed",
})
```

---

## Stage 8 — OAuthIntegrationStatus Transitions

The `OAuthIntegrationStatus` model drives the "reconnect" prompt in the UI. It must be kept accurate.

| Event | Status |
|---|---|
| OAuth flow initiated | `PENDING` |
| OAuth flow completed successfully | `CONNECTED` |
| Token refresh fails permanently | `ERROR` |
| User disconnects integration | `DISCONNECTED` |
| Re-authorization succeeds | `CONNECTED` |

Status updates must be made in the same transaction as the action that causes them.

---

## Stage 9 — Tests

Every stage must have test coverage before the integration is marked complete.

**Minimum test coverage:**

```
integrations/<provider>/tests/
  test_normalizer.py       — normalize() with representative payload samples
  test_oauth.py            — token exchange, refresh, error cases
  test_webhooks.py         — signature verification, deduplication, Celery dispatch
```

**Required test cases:**

```python
class NormalizerTests(TestCase):
    def test_normalize_returns_si_units(self): ...
    def test_normalize_maps_sport_to_canonical_slug(self): ...
    def test_normalize_missing_optional_fields_are_none_not_zero(self): ...
    def test_source_hash_is_deterministic(self): ...

class WebhookIngestionTests(TestCase):
    def test_invalid_signature_returns_400(self): ...
    def test_duplicate_event_is_idempotent(self): ...
    def test_valid_event_dispatches_celery_task(self): ...

class OAuthTests(TestCase):
    def test_token_exchange_stores_credential(self): ...
    def test_refresh_updates_credential(self): ...
    def test_refresh_failure_sets_error_status(self): ...
```

---

## Stage 10 — Monitoring and Alerting

Before enabling a provider in production:

1. **Sentry integration** — confirm all webhook and OAuth error paths call `logger.error()` or `logger.exception()` with `provider` and `organization_id` in `extra`.
2. **Alert model** — ensure `Alert` records are created on:
   - OAuth token refresh failure (blocks all future ingestion for this athlete)
   - Webhook signature verification failure (potential security event)
   - Activity normalization failure (data integrity risk)
3. **OAuthIntegrationStatus = ERROR** must trigger a UI prompt for the athlete to reconnect.
4. **Celery queue** — provider tasks must be routed to the `integrations` queue, not `default`.

---

## Stage 11 — Enable in Registry

Only after all previous stages are complete and CI is green:

```python
# core/providers/<provider>.py
class <Provider>Provider(IntegrationProvider):
    enabled = True  # Change False → True last
```

This is the production gate. `enabled = False` providers appear in the registry but reject all OAuth flows.

---

## Definition of Done

- [ ] `integrations/<provider>/` directory with `__init__.py`, `provider.py`, `normalizer.py`, `README.md`
- [ ] `core/providers/<provider>.py` registered in registry
- [ ] `"<provider>"` in `SUPPORTED_PROVIDERS`
- [ ] OAuth flow implemented and tested (`oauth2_login`, `oauth2_callback`)
- [ ] Token refresh implemented and tested
- [ ] Webhook ingestion implemented (or pull polling if no webhook support)
- [ ] Signature verification on all webhook endpoints
- [ ] `NormalizedActivity` with SI units and canonical sport slugs
- [ ] `ActivityStream` ingestion (if provider delivers time-series)
- [ ] Idempotency test: duplicate event does not create duplicate `CompletedActivity`
- [ ] `OAuthIntegrationStatus` transitions correct
- [ ] Structured logs on all error paths
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] CI green on push
- [ ] `enabled = True` set last, after all tests pass

---

## Quick Reference: Provider Status

| Provider | OAuth | Webhook | Pull | Enabled | Notes |
|---|---|---|---|---|---|
| Strava | 2.0 | Yes | Yes | Yes | Reference implementation |
| Garmin | **1.0a** | Yes | No | No | OAuth 1.0a — requires separate HMAC flow |
| Polar | 2.0 | Yes | No | No | Accesslink transaction model |
| COROS | 2.0 | No | Yes | No | Pull-only; rate limits apply |
| Suunto | 2.0 | Yes | No | No | Webhook-push architecture |
| Wahoo | 2.0 | Yes | Yes | No | Bidirectional: can push workouts to device |

---

## Related Documents

| Document | Purpose |
|---|---|
| [`docs/vendor/integration_architecture.md`](../../vendor/integration_architecture.md) | Provider architecture, idempotency guarantees, structured log fields |
| [`docs/domain/DOMAIN_MODEL.md`](../../domain/DOMAIN_MODEL.md) | Domain entity map — CompletedActivity, ActivityStream, ExternalIdentity |
| [`docs/ai/agents/integration_agent.md`](../agents/integration_agent.md) | Integration agent responsibilities and constraints |
| [`docs/ai/CONSTITUTION.md`](../CONSTITUTION.md) | Non-negotiable engineering laws |

---

*Last updated: 2026-03-07*
