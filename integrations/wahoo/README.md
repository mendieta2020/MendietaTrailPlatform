# Wahoo Cloud API Integration

**Status:** Coming Soon — pending vendor API access
**Provider ID:** `wahoo`
**Auth protocol:** OAuth 2.0

## Overview

Wahoo is a smart indoor trainer and cycling computer brand with strong B2B
partnership history. Integration enables Quantoryn to ingest Wahoo workout data
AND push structured training sessions to Wahoo ELEMNT devices — a key
bidirectional capability for coaching platforms.

## Authentication

Wahoo uses standard **OAuth 2.0 authorization code flow** via Wahoo Cloud API.

Required credentials:
- `WAHOO_CLIENT_ID`
- `WAHOO_CLIENT_SECRET`

## Capabilities

Wahoo is unique among supported providers in supporting **bidirectional integration**:

| Direction | Capability | Status |
|---|---|---|
| Inbound | Activity/workout data from ELEMNT/KICKR | Planned |
| Outbound | Structured workout push to ELEMNT device | Planned |

The outbound workout push capability enables Quantoryn to deliver coach-authored
training sessions directly to athlete devices for guided execution.

## Credentials Required

| Variable | Description |
|---|---|
| `WAHOO_CLIENT_ID` | OAuth 2.0 client ID |
| `WAHOO_CLIENT_SECRET` | OAuth 2.0 client secret |

## API Reference

- Wahoo Developer Portal: https://developer.wahooligan.com/

## Implementation Checklist

- [ ] Wahoo developer program access granted
- [ ] `integrations/wahoo/oauth.py` — OAuth 2.0 adapter
- [ ] `integrations/wahoo/mapper.py` — raw Wahoo workout JSON → normalized TypedDict
- [ ] `integrations/wahoo/normalizer.py` — sport type normalization
- [ ] `integrations/wahoo/workout_push.py` — structured workout delivery to ELEMNT
- [ ] `core/providers/wahoo.py` — set `enabled=True`, declare `supports_workout_push=True`
- [ ] `Actividad.Source.WAHOO` migration (added in this PR)
- [ ] `CompletedActivity.Provider.WAHOO` migration (added in this PR)
- [ ] End-to-end tests: OAuth flow, activity ingestion, workout push, idempotency
