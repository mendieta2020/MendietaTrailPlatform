# Quantoryn — Vendor API Access Kit

**Quantoryn** (codebase: MendietaTrailPlatform) is a scientific operating system for endurance
coaching organisations. This kit is prepared for API partnership review by Garmin, Suunto, Polar,
COROS, and Wahoo.

## What is in this kit

| Document | Purpose |
|---|---|
| [`platform_overview.md`](platform_overview.md) | What the product does, who uses it, core data flow, current provider status |
| [`vendor_data_access_spec.md`](vendor_data_access_spec.md) | **Data access specification** — what data we request, per-sport needs, Required vs Optional, Phase 1 vs Phase 2, justification mapping, user control |
| [`security_and_compliance.md`](security_and_compliance.md) | Token handling, CSRF/CORS, tenant isolation, logging policy |
| [`integration_architecture.md`](integration_architecture.md) | Provider-agnostic connect → ingest → normalize → reconcile flow |
| [`data_model_plan_vs_real.md`](data_model_plan_vs_real.md) | Why PlannedWorkout ≠ CompletedActivity; idempotency; auditability |
| [`strava_proof_of_integration.md`](strava_proof_of_integration.md) | End-to-end Strava OAuth + webhook evidence with file citations |
| [`vendor_requirements_checklist.md`](vendor_requirements_checklist.md) | DONE / PARTIAL / TODO per standard vendor requirement |
| [`email_templates.md`](email_templates.md) | Ready-to-send outreach and follow-up templates |

## How to review

1. Start with **platform_overview.md** for context.
2. Read **vendor_data_access_spec.md** for the data request scope and justification.
3. Read **security_and_compliance.md** and **integration_architecture.md** for technical due-diligence.
4. Use **strava_proof_of_integration.md** as the live evidence anchor.
5. Use **vendor_requirements_checklist.md** to assess readiness gaps.

## Repository structure at a glance

```
MendietaTrailPlatform/
├── backend/          # Django project settings, Celery config
├── core/             # Domain models, views, webhook handler, OAuth state
├── analytics/        # PMC, injury risk, training load analytics
├── integrations/
│   ├── strava/       # Strava-specific mapper, normalizer, OAuth adapter
│   └── outbound/     # Workout delivery (Garmin/COROS push — planned)
└── docs/
    ├── architecture.md
    ├── ADR-001-capability-based-provider-design.md
    └── vendor/       # ← this kit
```

## Contact

**Technical contact**: [TODO: engineering@yourdomain.com]
**Privacy / DPA contact**: [TODO: privacy@yourdomain.com]
**Company**: [TODO: Legal entity name]
**Website**: [TODO: https://yourdomain.com]
