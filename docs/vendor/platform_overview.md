# Platform Overview — Quantoryn

## What Quantoryn is

Quantoryn is **not a social network**. It is a **scientific operating system for endurance
coaching organisations** — designed to connect coach intent (training plan) with athlete reality
(completed activity) and close the feedback loop through evidence-based analytics.

Primary users: endurance coaches managing between 10 and 200 athletes across trail running,
road cycling, mountain biking, triathlon, and open-water swimming.

## Core data flow

```
1. PLAN      Coach creates a structured workout
             → core/models.py: Entrenamiento + BloqueEntrenamiento + PasoEntrenamiento

2. EXECUTE   Athlete performs the workout on their device
             → activity data leaves via Strava (live) or future providers

3. INGEST    Provider webhook / backfill delivers raw activity
             → core/webhooks.py: StravaWebhookView
             → core/tasks.py: process_strava_event (Celery)
             → core/models.py: Actividad (source of truth for real data)

4. NORMALIZE Provider-specific payload is mapped to the platform schema
             → integrations/strava/mapper.py
             → integrations/strava/normalizer.py

5. RECONCILE Completed activity is matched to the planned workout
             → Actividad.reconciled_at / reconciliation_score / reconciliation_method
             → analytics/plan_vs_actual.py

6. ANALYSE   Canonical training load, PMC (CTL/ATL/TSB), injury risk
             → analytics/pmc_engine.py
             → analytics/injury_risk.py

7. ALERT     Coach receives signals when athlete deviates from plan
             → analytics/alerts.py

8. ADAPT     Coach updates plan for next cycle
             → back to step 1
```

## Disciplines supported

| Sport key | Label |
|---|---|
| `RUN` | Road running |
| `TRAIL` | Trail running / mountain |
| `CYCLING` | Road cycling |
| `MTB` | Mountain bike |
| `SWIMMING` | Open water / pool |
| `STRENGTH` | Gym / resistance |
| `CARDIO` | Cross-training |
| `INDOOR_BIKE` | Trainer / smart roller |
| `REST` | Active rest day |
| `OTHER` | Catch-all |

Source: `TIPO_ACTIVIDAD` constant — `core/models.py:28`

## Provider status

| Provider | Status | Evidence |
|---|---|---|
| **Strava** | **Production — live** | `integrations/strava/`, `core/webhooks.py`, `core/integration_models.py` |
| Garmin | Planned — architecture ready | `core/provider_capabilities.py`, `core/providers.py` |
| COROS | Planned — architecture ready | same |
| Suunto | Planned — architecture ready | same |
| Polar | Planned — architecture ready | same |
| Wahoo | Planned — architecture ready | same |

The platform was designed from day one for multiple providers. Provider-specific code is
isolated in `integrations/<provider>/`; the domain model (`Actividad`, `CompletedActivity`,
`OAuthCredential`, `OAuthIntegrationStatus`, `ExternalIdentity`) is provider-agnostic.

## What Quantoryn does NOT do

- No public activity feed or social sharing.
- No athlete-to-athlete communication.
- No advertising or data monetisation.
- No sale or transfer of athlete data to third parties.
- Raw provider payloads are retained for audit / re-processing only; they are never
  exposed outside the coach's organisation boundary.
