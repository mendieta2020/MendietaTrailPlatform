# Polar Accesslink Integration

**Status:** Coming Soon — pending vendor API access
**Provider ID:** `polar`
**Auth protocol:** OAuth 2.0

## Overview

Polar is a leading heart rate and endurance performance device brand.
Integration enables Quantoryn to ingest Polar training sessions and heart rate
data into the coaching platform via the Polar Accesslink API.

## Authentication

Polar uses standard **OAuth 2.0 authorization code flow** via Polar Accesslink.

Required credentials:
- `POLAR_CLIENT_ID`
- `POLAR_CLIENT_SECRET`

## Activity Ingestion

Polar Accesslink uses a **transaction-based pull model**:

1. `register_user` — register athlete with Accesslink on first connect
2. `list_transactions` — poll for new exercise transactions
3. `get_exercise_summary` — fetch individual activity details
4. `commit_transaction` — mark transaction as consumed (idempotency)

This differs from Strava's webhook push model. A Celery polling task handles
transaction consumption.

## Credentials Required

| Variable | Description |
|---|---|
| `POLAR_CLIENT_ID` | OAuth 2.0 client ID |
| `POLAR_CLIENT_SECRET` | OAuth 2.0 client secret |

## API Reference

- Polar Accesslink API: https://www.polar.com/accesslink-api/
- Polar Developer Portal: https://developer.polar.com/

## Implementation Checklist

- [ ] Polar Accesslink API developer access granted
- [ ] `integrations/polar/oauth.py` — OAuth 2.0 adapter
- [ ] `integrations/polar/mapper.py` — ExerciseSummary → normalized TypedDict
- [ ] `integrations/polar/normalizer.py` — sport type normalization
- [ ] `core/tasks.py` — `poll_polar_transactions_for_athlete` Celery task
- [ ] `core/providers/polar.py` — set `enabled=True`
- [ ] `Actividad.Source.POLAR` migration (added in this PR)
- [ ] `CompletedActivity.Provider.POLAR` migration (added in this PR)
- [ ] End-to-end tests: OAuth flow, transaction model, idempotency
