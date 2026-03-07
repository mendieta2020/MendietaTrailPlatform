# COROS Open Platform Integration

**Status:** Coming Soon — pending vendor API access
**Provider ID:** `coros`
**Auth protocol:** OAuth 2.0

## Overview

COROS is an emerging GPS sports watch brand with strong presence in trail running,
triathlon, and ultra-endurance communities. Integration enables Quantoryn to ingest
COROS device activities into the coaching platform.

## Authentication

COROS uses standard **OAuth 2.0 authorization code flow** via COROS Open Platform.

Required credentials:
- `COROS_CLIENT_ID`
- `COROS_CLIENT_SECRET`

## Activity Ingestion

COROS Open Platform provides REST API endpoints for activity list and detail retrieval.
A Celery polling task or webhook subscription (if available) handles ingestion.

## Credentials Required

| Variable | Description |
|---|---|
| `COROS_CLIENT_ID` | OAuth 2.0 client ID |
| `COROS_CLIENT_SECRET` | OAuth 2.0 client secret |

## API Reference

- COROS Open Platform: https://open.coros.com/

## Implementation Checklist

- [ ] COROS Open Platform developer access granted
- [ ] `integrations/coros/oauth.py` — OAuth 2.0 adapter
- [ ] `integrations/coros/mapper.py` — raw COROS activity JSON → normalized TypedDict
- [ ] `integrations/coros/normalizer.py` — sport type normalization
- [ ] `core/tasks.py` — ingestion task (polling or webhook-based)
- [ ] `core/providers/coros.py` — set `enabled=True`
- [ ] `Actividad.Source.COROS` migration (already present)
- [ ] End-to-end tests: OAuth flow, activity ingestion, idempotency
