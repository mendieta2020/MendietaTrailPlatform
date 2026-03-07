# Garmin Connect Integration

**Status:** Coming Soon — pending vendor API access
**Provider ID:** `garmin`
**Auth protocol:** OAuth 1.0a (not OAuth 2.0)

## Overview

Garmin Connect is the largest endurance sports platform by device installed base.
Integration enables Quantoryn to ingest Garmin device activities (running, cycling,
triathlon) directly into the coaching platform.

## Authentication

Garmin uses **OAuth 1.0a**, which differs from all other supported providers.

Implementation requires:
- `requests-oauthlib` for the three-legged OAuth 1.0a handshake
- `GARMIN_CONSUMER_KEY` and `GARMIN_CONSUMER_SECRET` in environment variables
- A temporary request token exchange before user redirect (unlike OAuth 2.0)

Access tokens in OAuth 1.0a do not expire — there is no refresh token flow.

## Activity Ingestion

Garmin's public API does not support webhooks. Activity sync uses **polling**:

1. On athlete connect: backfill last N days of activities
2. Periodic polling task (Celery beat) checks for new activities

## Credentials Required

| Variable | Description |
|---|---|
| `GARMIN_CONSUMER_KEY` | OAuth 1.0a consumer key |
| `GARMIN_CONSUMER_SECRET` | OAuth 1.0a consumer secret |

## API Reference

- Garmin Connect Developer Program: https://developer.garmin.com/gc-developer-program/overview/
- Garmin Health API: https://developer.garmin.com/health-api/overview/

## Implementation Checklist

- [ ] Garmin Developer Program access granted
- [ ] `integrations/garmin/oauth.py` — OAuth 1.0a adapter (requests-oauthlib)
- [ ] `integrations/garmin/mapper.py` — raw activity JSON → normalized business TypedDict
- [ ] `integrations/garmin/normalizer.py` — sport type normalization
- [ ] `core/tasks.py` — `poll_garmin_activities_for_athlete` Celery task
- [ ] `core/providers/garmin.py` — set `enabled=True`, implement `fetch_activities`
- [ ] `Actividad.Source.GARMIN` migration (already present)
- [ ] End-to-end tests: OAuth flow, activity ingestion, idempotency
