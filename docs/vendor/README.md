# Quantoryn — Vendor API Access Kit

**Quantoryn** is a scientific operating system for endurance coaching organisations.
This kit is prepared for API partnership review by Garmin, Suunto, Polar, COROS, and Wahoo.

**Location**: Córdoba, Argentina
**Partnerships**: partnerships@quantoryn.com

---

## Outreach documents (vendor-facing)

Start here. These documents are written for business, legal, and partnership teams.

| Document | Purpose |
|---|---|
| [`quantoryn-overview.md`](quantoryn-overview.md) | Platform philosophy, architecture principles, supported sports, provider status |
| [`integration-architecture.md`](integration-architecture.md) | How providers connect, ingest, and normalise into Quantoryn — no code references |
| [`data-handling.md`](data-handling.md) | OAuth token lifecycle, webhook ingestion, provider isolation, data classification, retention |
| [`privacy-policy.md`](privacy-policy.md) | How athlete data is collected, stored, and protected |
| [`terms-of-service.md`](terms-of-service.md) | Platform usage terms, athlete data ownership, liability |
| [`vendor-contact.md`](vendor-contact.md) | Official contacts, partnership request process, response SLAs |

---

## Technical evidence kit (engineering review)

Detailed documents with codebase citations for vendor engineering and security teams.

| Document | Purpose |
|---|---|
| [`platform_overview.md`](platform_overview.md) | Core data flow with module references |
| [`vendor_data_access_spec.md`](vendor_data_access_spec.md) | Data access spec — Required vs Optional fields, per-sport needs, Phase 1 vs Phase 2 scope |
| [`integration_architecture.md`](integration_architecture.md) | End-to-end flow with exact endpoints, file paths, idempotency guarantees |
| [`security_and_compliance.md`](security_and_compliance.md) | CORS/CSRF/ALLOWED_HOSTS, token handling, rate limits — with settings citations |
| [`data_model_plan_vs_real.md`](data_model_plan_vs_real.md) | Plan ≠ Real domain model; `CompletedActivity` fields and unique constraint |
| [`strava_proof_of_integration.md`](strava_proof_of_integration.md) | Live Strava integration evidence: endpoints, tests, 338-test suite status |
| [`vendor_requirements_checklist.md`](vendor_requirements_checklist.md) | 26 DONE / 5 PARTIAL / 7 TODO across Legal, Security, OAuth, Data handling, Operational |
| [`email_templates.md`](email_templates.md) | Ready-to-send outreach and follow-up templates |

---

## Compliance documents

Full legal and policy documents.

| Document | Purpose |
|---|---|
| [`../compliance/privacy_policy.md`](../compliance/privacy_policy.md) | Full privacy policy with data subject rights |
| [`../compliance/terms_of_service.md`](../compliance/terms_of_service.md) | Full terms of service |
| [`../compliance/security_policy.md`](../compliance/security_policy.md) | Security contact, responsible disclosure, incident response |

---

## Recommended review path

**For business / BD / legal teams:**
1. `quantoryn-overview.md`
2. `data-handling.md`
3. `privacy-policy.md`
4. `terms-of-service.md`
5. `vendor-contact.md` to initiate partnership

**For engineering / security teams:**
1. `integration-architecture.md`
2. `vendor_data_access_spec.md`
3. `security_and_compliance.md`
4. `strava_proof_of_integration.md`
5. `vendor_requirements_checklist.md` for gap assessment

---

## Repository structure

```
MendietaTrailPlatform/
├── backend/          # Django project settings, Celery config
├── core/             # Domain models, views, webhook handler, OAuth state
├── analytics/        # PMC, injury risk, training load analytics
├── integrations/
│   ├── strava/       # Strava mapper, normaliser, OAuth adapter (live)
│   └── outbound/     # Structured workout delivery (roadmap)
└── docs/
    ├── architecture.md
    ├── ADR-001-capability-based-provider-design.md
    ├── compliance/   # Privacy policy, ToS, security policy
    └── vendor/       # ← this kit
```
