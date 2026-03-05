# Vendor Data Access Specification — Quantoryn

**Version**: 1.0
**Date**: 2026-03-05
**Applies to**: Garmin, Suunto, Polar, COROS, Wahoo API partnership reviews
**Contact**: engineering@quantoryn.com

---

## A. Executive Summary

Quantoryn is a scientific coaching operating system for endurance sports organisations.
It is not a consumer app, a social network, or a data marketplace.

We are requesting API access to enable **two strictly bounded use cases**:

1. **Plan vs Real reconciliation** — matching what the coach prescribed against what the
   athlete actually executed, using normalised activity summaries.
2. **Performance analytics and heatmaps** — terrain-aware pacing analysis, training zone
   mapping over routes, and route density heatmaps for coach decision support.

**Governing principles for this request:**

| Principle | How we apply it |
|---|---|
| **Purpose limitation** | Data is used exclusively for coaching analytics within the athlete's own organisation. No advertising, no profiling, no resale. |
| **Data minimisation** | We separate Required (features break without it) from Optional (enrichment). We do not request data we have no feature roadmap for. |
| **Athlete control** | Athletes can disconnect their provider account at any time. All their imported data can be deleted on request. |
| **Organisational boundary** | Data never crosses tenant boundaries. A coach can only access data for athletes within their own organisation. |
| **No third-party sharing** | Raw provider data is never transmitted to any third party outside the coach–athlete organisation. |

---

## B. Data Categories Requested

### B.1 Activity summary (all providers, all sports)

These fields are the **minimum viable** set. They power Plan vs Real reconciliation and
basic training load tracking without requiring full time-series streams.

| Field | Required / Optional | Notes |
|---|---|---|
| Activity ID (provider-assigned) | **Required** | Idempotency key — prevents duplicate ingestion |
| Sport type | **Required** | Maps to `TIPO_ACTIVIDAD` in Quantoryn schema |
| Start timestamp (UTC) | **Required** | Temporal anchor for Plan vs Real matching |
| Total duration (seconds) | **Required** | Training load denominator |
| Total distance (metres) | **Required** | Volume metric |
| Total elevation gain (metres) | **Required** | Load correction for trail/mountain sports |
| Total elevation loss (metres) | Optional | Terrain balance; used in trail coaching |
| Average heart rate (bpm) | **Required** | TRIMP / HR-based load calculation |
| Max heart rate (bpm) | Optional | Zone ceiling verification |
| Average power (watts) | **Required** (cycling) | TSS calculation; required for all cycling sports |
| Max power (watts) | Optional | Sprint/peak analysis |
| Normalised power (watts) | Optional | Reduces TSS calculation burden |
| Average cadence (rpm / spm) | Optional | Running economy; cycling efficiency |
| Calories (kcal) | Optional | Energy balance; not used in load model |
| Device / hardware model | Optional | Data quality attribution |

### B.2 Activity streams (time-series, per-second or per-interval)

Streams are required for **heatmaps** and **pacing performance analytics**.
We acknowledge streams are larger payloads and we commit to the minimisation options
described in Section E (Phase 1 vs Phase 2).

| Stream | Required / Optional | Sampling | Purpose |
|---|---|---|---|
| GPS coordinates (lat, lng) | **Required** for heatmaps | 1 Hz or simplified polyline | Route reconstruction, heatmap density, terrain overlay |
| Altitude (metres, GPS-derived) | **Required** for terrain analytics | Same as GPS | Pacing vs elevation correlation, grade computation |
| Heart rate (bpm) | **Required** for pacing analytics | 1 Hz acceptable | Pacing vs HR; zone time distribution over route segments |
| Power (watts) | **Required** (cycling) | 1 Hz acceptable | Pacing vs power; TSS by segment |
| Speed / pace (m/s) | **Required** | 1 Hz acceptable | Pacing analysis core metric |
| Cadence (rpm / spm) | Optional | 1 Hz acceptable | Running economy over terrain segments |
| Grade (%) | Optional (derive from alt+GPS) | Derived | Can be computed; preferred if available natively |
| Temperature (°C) | Optional | 1 Hz or summary | Environmental context for performance |
| Respiration rate | Optional | 1 Hz or summary | Roadmap: recovery analytics |

**Why full streams and not only summary fields?**

Terrain-aware pacing analytics require correlating instantaneous pace, HR, power, and
altitude at the same timestamp. Summary averages lose the within-activity signal that
differentiates, for example, a flat 10 km at 5:00/km from a mountainous 10 km at 5:00/km
average. Scientific coaching and AI-assisted coaching features are not possible with
summaries alone.

---

## C. Per-Sport Data Needs

### C.1 Running (Road) and Trail Running

Trail running is Quantoryn's core focus discipline. Heatmap and terrain analytics are
primary P0 features for this sport.

| Data need | Required / Optional | Justification |
|---|---|---|
| GPS stream (lat, lng, alt) | **Required** | Route heatmap; terrain-aware pacing; grade computation |
| HR stream | **Required** | Pacing vs HR analysis; aerobic efficiency over terrain |
| Pace/speed stream | **Required** | Core pacing analysis |
| Cadence stream | Optional | Running economy; stride efficiency |
| Elevation gain (summary) | **Required** | Trail load correction (terrain multiplier) |
| Activity summary (all fields above) | **Required** | Plan vs Real reconciliation |

### C.2 Road Cycling

| Data need | Required / Optional | Justification |
|---|---|---|
| Power stream | **Required** | TSS calculation; pacing vs power analysis; FTP tracking |
| HR stream | **Required** | HR-based load fallback; cardiac drift analysis |
| Speed stream | **Required** | Velocity-terrain correlation |
| GPS stream | **Required** | Route heatmap; elevation profile |
| Cadence stream | Optional | Pedalling efficiency; fatigue indicators |
| Normalised power (summary) | Optional | Reduces server-side TSS computation |

### C.3 Mountain Biking (MTB)

Same data needs as road cycling. Elevation and GPS streams are especially important
for terrain classification and descent/climb segment analysis.

| Data need | Required / Optional | Notes |
|---|---|---|
| GPS stream (lat, lng, alt) | **Required** | Technical terrain analysis |
| Power stream | Optional | Not all MTB athletes use power meters |
| HR stream | **Required** | Primary load metric when power unavailable |
| Speed stream | **Required** | Pacing analysis |

### C.4 Strength Training

Strength sessions do not require GPS or streaming data.

| Data need | Required / Optional | Notes |
|---|---|---|
| Activity summary (sport, duration) | **Required** | Plan vs Real reconciliation |
| Exercise list (name, sets, reps, weight) | Optional | Structured strength plan compliance |
| Heart rate (summary: avg, max) | Optional | Session intensity proxy |

GPS stream: **not requested** for strength training.

### C.5 Roadmap: Triathlon

Not yet in production. When implemented, data needs per segment (swim, bike, run) follow
the patterns above. Transition time summaries required for multi-sport TSS.

### C.6 Roadmap: Swimming

Not yet in production. Anticipated needs: pool/open-water summary, lap count, SWOLF,
stroke count, distance per stroke. No GPS stream required for pool swimming.

---

## D. Justification Mapping Table

| Data element | Why needed | Feature enabled | Risk | Mitigation |
|---|---|---|---|---|
| GPS coordinates stream | Route reconstruction for heatmaps; terrain gradient computation | Route heatmaps, terrain-aware pacing, route density | Location privacy | Data stays within athlete's org; no public sharing; athlete can delete |
| GPS altitude stream | Grade computation; elevation profile per route | Pacing vs elevation, trail load model | Low | Derives from existing GPS; no additional sensitivity |
| HR stream (time-series) | Correlate HR with pace and terrain at segment level | Pacing vs HR, zone time over route, aerobic drift detection | Low | Stored in `datos_brutos`; org-scoped; never shared |
| Power stream (cycling) | Segment-level TSS; identify climbs vs flats in effort distribution | Pacing vs power, FTP segment analysis | Low | Same storage scope as HR |
| Speed/pace stream | Core pacing analysis metric | Pacing analytics (all sports) | None | Derived from GPS if not provided natively |
| Activity summary (sport, start, duration, distance, elevation) | CompletedActivity model backbone | Plan vs Real reconciliation, training load | None | Minimum field set; stored in normalised columns |
| Avg/max HR (summary) | TRIMP fallback when stream unavailable | Training load, canonical load method | None | Used only when stream not available |
| Avg/max power (summary) | TSS fallback; FTP tracking | Cycling training stress | None | Used only when stream not available |
| Provider activity ID | Idempotency key | Prevents duplicate ingestion on re-delivery | None | Stored as opaque string; not exposed to other orgs |
| Device model | Data quality attribution; stream resolution awareness | Coaching context | None | Not displayed to athletes; internal metadata only |
| Exercise list (strength) | Plan vs Real for structured strength sessions | Strength coaching compliance | None | Optional; only requested if provider offers structured workout data |

---

## E. Scope Strategy: Phase 1 vs Phase 2

### Phase 1 — Minimum viable vendor approval (immediate request)

Goal: get approved and live. Request the smallest data surface that enables the core
coaching features.

| Data | Scope |
|---|---|
| Activity summary (all sports) | Full — required for Plan vs Real |
| GPS polyline (simplified, not raw stream) | Simplified polyline or 10-second sampled stream — sufficient for heatmap tiles and elevation profile |
| HR summary (avg, max) | Required — enables TRIMP-based load calculation |
| Power summary (avg, normalised — cycling) | Required — enables TSS |
| HR stream | Phase 1 included — needed for pacing vs HR |
| Power stream (cycling) | Phase 1 included — needed for pacing vs power |
| Speed/pace stream | Phase 1 included — needed for pacing analytics |
| Cadence stream | Deferred to Phase 2 |
| Temperature stream | Deferred to Phase 2 |
| Respiration stream | Deferred to Phase 2 |

**Minimisation offer for Phase 1**: If the provider requires stream access to be limited
at initial approval, we can operate with a 10-second GPS sample interval (vs 1 Hz) for
heatmap tile generation. HR and power streams at 1 Hz are required for the correlation
analytics; we cannot downsample these without losing scientific validity.

### Phase 2 — Advanced features (follow-on access request)

| Data added | Feature unlocked |
|---|---|
| Full 1 Hz GPS stream | Fine-grained route replay; precise terrain classification |
| Cadence stream (run + bike) | Running economy; cycling efficiency over segments |
| Temperature stream | Environmental performance context |
| Respiration stream | Recovery analytics; HRV-adjacent signals |
| Structured workout result (strength) | Strength plan compliance analytics |

---

## F. Storage and Retention

Storage infrastructure is documented in `docs/compliance/privacy_policy.md` §4.
Security posture and token handling are documented in `docs/compliance/security_policy.md`.

Summary relevant to data access:

- **Primary database**: PostgreSQL (Railway-managed). All normalised activity fields
  stored in `Actividad` and `CompletedActivity` tables.
- **Raw payload**: Stored verbatim in `datos_brutos` (JSON column) on `Actividad` and
  `raw_payload` on `CompletedActivity` for audit and future re-processing.
  Never transmitted outside the platform.
- **Cache**: Redis (Railway-managed). Used for OAuth nonces (15-min TTL) and Celery
  task queue only. No activity data stored in Redis.
- **Retention**: Activity data is retained for as long as the athlete record is active.
  Data is cascade-deleted when an athlete record is removed.
- **Formal retention schedule**: TODO — per-field schedule to be published.
  See `p1/data-retention-policy`.

---

## G. User Control

### G.1 Revoke access (implemented)

Athletes can disconnect their provider integration at any time:

```
POST /api/integrations/{provider}/disconnect/
```

This revokes the OAuth token at the provider, zeros the stored credentials, and sets
the integration status to DISCONNECTED. The `ExternalIdentity` record is disabled.
Future webhook events from the provider for that athlete will be ignored.

Source: `core/integration_views.py` — `IntegrationDisconnectView`

### G.2 Data deletion (partially implemented)

- **Cascade delete**: removing an athlete record from the organisation deletes all
  associated `Actividad`, `CompletedActivity`, `OAuthCredential`, and
  `OAuthIntegrationStatus` rows via Django CASCADE.
- **Email request**: athletes or coaches can request full data deletion by emailing
  `privacy@quantoryn.com`. Actioned within 30 days.
- **Self-service deletion API**: not yet implemented.
  Planned: `p1/data-deletion-request-api`.

### G.3 Scope of data held per athlete

When integrated with a provider, Quantoryn holds:

1. OAuth access token + refresh token (PostgreSQL, `OAuthCredential` table).
2. Normalised activity records (fields listed in Section B.1).
3. Raw provider payload (JSON blob, for audit).
4. GPS polyline or stream (if stream access granted).
5. HR/power streams (if stream access granted).

Nothing is held beyond what is described above.

---

## H. Security Posture Summary

Full security documentation: `docs/compliance/security_policy.md`

| Control | Status |
|---|---|
| OAuth 2.0 with HMAC-signed state | Implemented — `core/oauth_state.py` |
| Single-use nonce replay protection | Implemented — Redis-backed, 15-min TTL |
| Tokens never logged | Implemented — `integrations/strava/oauth.py` sanitises output |
| Multi-tenant fail-closed isolation | Implemented — `TenantContextMiddleware` + non-nullable org FK |
| Rate limiting on all API surfaces | Implemented — `core/throttling.py` |
| CORS whitelist (no wildcard) | Implemented — `CORS_ALLOW_ALL_ORIGINS = False` |
| Webhook verification token (fail-closed) | Implemented — `core/webhooks.py` |
| Idempotent ingestion (duplicate-safe) | Implemented — `UniqueConstraint` on `(organization, provider, provider_activity_id)` |
| Token encryption at rest | **TODO** — `p1/encrypt-oauth-tokens-at-rest` |
| Formal incident response runbook | **TODO** — `p1/incident-response-runbook` |

Security contact: **security@quantoryn.com**

---

## I. Provider-Specific Notes

This specification is intentionally provider-agnostic. The architecture supports adding
any new provider via `integrations/<provider>/` without changes to the domain model.

**What we have implemented (Strava only — live in production):**
- OAuth 2.0 connect / disconnect
- Webhook event ingestion (activity create / update / delete)
- Historical backfill on connect
- Activity normalisation (sport type, units, elevation)

**What we have architected but not yet implemented for non-Strava providers:**
- OAuth credential storage: `OAuthCredential` model is provider-agnostic and ready
- Integration status tracking: `OAuthIntegrationStatus` supports any provider key
- Provider capability registry: `core/provider_capabilities.py` defines which
  capabilities (webhooks, backfill, workout push) each provider supports
- Outbound workout delivery: `integrations/outbound/workout_delivery.py` (planned)

We will not claim live integration status for any provider until it is production-verified
and tested. This document describes the data we intend to request upon approval;
implementation will follow the Strava integration pattern.
