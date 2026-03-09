# Quantoryn — Platform Overview

**Category**: Endurance Training Platform
**Location**: Córdoba, Argentina
**Contact**: partnerships@quantoryn.com

---

## What Quantoryn is

Quantoryn is a scientific operating system for endurance coaching organizations.

It is not a consumer fitness app. It is not a social network. It is a private, organisation-scoped
platform that gives coaches a structured, evidence-based view of how their athletes are training
and how reality compares to the prescription.

---

## Problem it solves

Endurance coaches manage between 10 and 200 athletes simultaneously. They write structured training
plans and assign them to athletes. Athletes execute those plans using wearable devices and GPS
watches. The coach rarely has a reliable, consolidated view of whether execution matched intent —
and when it does not, the analytical tools to understand why are absent.

Quantoryn closes that gap by:

1. Connecting to provider APIs (Strava live; Garmin, COROS, Polar, Suunto, Wahoo under partnership review)
2. Ingesting completed activities automatically via webhooks and backfill
3. Normalising provider data to a unified coaching schema
4. Comparing planned workouts against completed activities
5. Applying scientific load models (PMC, TSS/TRIMP, injury risk) to the result
6. Surfacing coach-facing alerts and analytics when athletes deviate from plan

---

## Core coaching loop

```
PLAN → EXECUTE → INGEST → NORMALISE → RECONCILE → ANALYSE → ALERT → ADAPT
```

| Stage | Description |
|---|---|
| **Plan** | Coach creates structured sessions: sport, duration, zones, intervals |
| **Execute** | Athlete performs the session on their device |
| **Ingest** | Provider API delivers the completed activity (webhook or backfill) |
| **Normalise** | Raw provider payload is mapped to the platform's unified schema |
| **Reconcile** | Completed activity is matched to its planned counterpart |
| **Analyse** | Training load, PMC curve, injury risk, zone distribution computed |
| **Alert** | Coach is notified of significant deviations from plan |
| **Adapt** | Coach adjusts future sessions based on the evidence |

---

## Architecture principles

**Multi-tenant, fail-closed organisation model**
Every data record — plan, activity, credential — is scoped to a coach organisation.
Cross-organisation data access is architecturally impossible, not just policy-controlled.

**Plan ≠ Real**
Planned workouts and completed activities are separate domain objects. They are never merged
into a single record. Reconciliation is an explicit, versioned operation with a confidence score.

**Provider-agnostic integrations layer**
All provider-specific logic (payload mapping, OAuth flow, normalisation) lives in an isolated
`integrations/<provider>/` module. The coaching domain layer has no direct dependency on any
provider's API format. Adding a new provider requires no changes to the core domain.

**Structured observability**
Every integration event carries structured log fields: `provider`, `outcome`, `reason_code`,
`organization_id`. Nothing related to tokens or secrets appears in any log.

**Reproducible scientific analytics**
All load calculations are versioned. Raw provider payloads are preserved for audit and
re-processing. Recalculating a metric with a new algorithm version does not destroy historical data.

---

## Supported sports

| Sport | Status |
|---|---|
| Trail Running | Production |
| Road Running | Production |
| Road Cycling | Production |
| Mountain Biking | Production |
| Indoor Cycling / Smart Trainer | Production |
| Strength Training | Production |
| Cross-Training / Cardio | Production |
| Triathlon | Roadmap |
| Open-Water Swimming | Roadmap |

---

## Provider status

| Provider | Status |
|---|---|
| Strava | Live in production |
| Garmin | Architecture ready, integration pending approval |
| COROS | Architecture ready, integration pending approval |
| Polar | Architecture ready, integration pending approval |
| Suunto | Architecture ready, integration pending approval |
| Wahoo | Architecture ready, integration pending approval |

---

## What Quantoryn does not do

- No public activity feed or social sharing between athletes.
- No advertising of any kind.
- No sale, transfer, or monetisation of athlete data.
- No third-party analytics platforms receive athlete data.
- No cross-organisation data access under any conditions.

---

## Deeper reading

| Document | Content |
|---|---|
| Integration Architecture | How providers connect, ingest, and normalize into the platform |
| Data Handling | OAuth lifecycle, webhook ingestion, retention philosophy |
| Privacy Policy | How athlete data is collected, stored, and protected |
| Terms of Service | Platform usage terms |
| Vendor Contact | Official contact information |
