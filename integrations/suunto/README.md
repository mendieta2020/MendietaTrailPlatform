# Suunto Sports Tracking Services Integration

**Status:** Coming Soon — pending vendor API access
**Provider ID:** `suunto`
**Auth protocol:** OAuth 2.0

## Overview

Suunto is a Finnish sports watch brand known for trail running, diving, and
alpine sports. Integration enables Quantoryn to ingest Suunto training sessions
into the coaching platform via the Suunto Sports Tracking Services (STS) API.

## Authentication

Suunto uses standard **OAuth 2.0 authorization code flow** via Suunto STS.

Required credentials:
- `SUUNTO_CLIENT_ID`
- `SUUNTO_CLIENT_SECRET`

## Activity Ingestion

Suunto STS supports **webhook subscriptions** for near-real-time activity delivery,
making it architecturally similar to Strava. The existing `StravaWebhookView`
pattern can serve as the reference implementation.

Webhook delivery model:
1. Register webhook subscription (one-time setup)
2. Suunto POSTs to `integrations/suunto/webhook/` on new activity
3. Celery task processes payload and ingests activity

## Credentials Required

| Variable | Description |
|---|---|
| `SUUNTO_CLIENT_ID` | OAuth 2.0 client ID |
| `SUUNTO_CLIENT_SECRET` | OAuth 2.0 client secret |
| `SUUNTO_WEBHOOK_SECRET` | Webhook signature verification secret |

## API Reference

- Suunto Developer Program: https://www.suunto.com/en-gb/sports-tech/suunto-developer-program/

## Implementation Checklist

- [ ] Suunto developer program access granted
- [ ] `integrations/suunto/oauth.py` — OAuth 2.0 adapter
- [ ] `integrations/suunto/mapper.py` — workoutSummary → normalized TypedDict
- [ ] `integrations/suunto/normalizer.py` — sport type normalization
- [ ] `integrations/suunto/webhook.py` — webhook handler (mirrors Strava pattern)
- [ ] `core/providers/suunto.py` — set `enabled=True`
- [ ] `Actividad.Source.SUUNTO` migration (already present)
- [ ] End-to-end tests: OAuth flow, webhook ingestion, idempotency
