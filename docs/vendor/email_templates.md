# Email Templates — Vendor API Access Outreach

---

## Template A — Initial API Access Request

> **Instructions**: Replace all `[PLACEHOLDER]` values before sending.
> Attach: `platform_overview.md`, `integration_architecture.md`, `strava_proof_of_integration.md`.

---

**Subject**: API Partnership Request — Quantoryn Endurance Coaching Platform

Dear [VENDOR] Developer Partnerships Team,

My name is [YOUR NAME], and I am the technical lead at [COMPANY LEGAL NAME], the team behind
**Quantoryn** — a scientific coaching operating system for endurance sports organisations.

We are requesting API access (and webhook / push access where available) for the
**[VENDOR] platform** to power real-time activity ingestion for the athletes managed by our
coaching clients.

**What Quantoryn does**

Quantoryn connects structured training plans (created by coaches) with completed activities
(delivered by provider APIs) and applies evidence-based analytics — training load,
performance management chart (CTL/ATL/TSB), and injury risk — to close the coaching
feedback loop. It is not a social network; it is a private, organisation-scoped platform.

**Current production status**

- Strava OAuth + webhook integration: live in production
- Architecture supports Garmin, Suunto, COROS, Polar, and Wahoo via a provider-agnostic
  framework (documented in the attached architecture overview)

**Technical readiness highlights**

- OAuth 2.0 with HMAC-signed state, single-use nonces, and Redis-backed replay protection
- Idempotent webhook ingestion (duplicate events are safely ignored)
- Strict multi-tenant data isolation: every activity row is organisation-scoped and
  fail-closed — no cross-tenant data access is possible
- Provider-specific logic is fully isolated in `integrations/<provider>/`
- 338 automated tests passing

**What we are requesting**

- Access to [VENDOR]'s [Health/Activity/Webhook] API
- OAuth application credentials (client_id / client_secret)
- Webhook push registration (if available)
- Review of our technical documentation at [DOCS URL or attached PDFs]

**Documentation attached**

1. Platform Overview
2. Integration Architecture
3. Strava Proof of Integration (reference live implementation)

We are happy to complete any technical questionnaire, DPA, or security review your team
requires. Our privacy policy is available at [https://yourdomain.com/privacy] and our terms
of service at [https://yourdomain.com/terms].

Please let me know how to proceed.

Best regards,
[YOUR NAME]
[TITLE]
[COMPANY LEGAL NAME]
[engineering@yourdomain.com]
[https://yourdomain.com]

---

## Template B — Follow-up with Technical Evidence and Questionnaire Readiness

> **Instructions**: Send 5–7 business days after Template A if no reply, or immediately after
> an initial response asking for more detail.
> Attach: full `docs/vendor/` kit as PDF or share a link to the docs folder.

---

**Subject**: Re: API Partnership Request — Quantoryn [Follow-up + Technical Evidence]

Dear [CONTACT NAME / Partnerships Team],

Following up on my request dated [DATE] regarding API access for Quantoryn.

I am sharing our full **Vendor Technical Kit** which documents our integration architecture,
security posture, and implementation evidence. Here is a quick index:

| Document | Content |
|---|---|
| Platform Overview | What Quantoryn is, core data flow, supported sports |
| Security & Compliance | Token handling, CORS/CSRF, tenant isolation, logging policy |
| Integration Architecture | Connect → ingest → normalize → reconcile flow, idempotency |
| Plan vs Real Data Model | Separation of planned workouts and completed activities |
| Strava Proof of Integration | End-to-end live implementation with file citations and test evidence |
| Vendor Requirements Checklist | DONE / PARTIAL / TODO against standard requirements |

**Links / attachments**: [ATTACH DOCS OR SHARE LINK TO https://yourdomain.com/vendor-kit]

**Answers to common questionnaire questions**

| Question | Answer |
|---|---|
| Do you store access tokens? | Yes — encrypted at rest in PostgreSQL [TODO: confirm field-level encryption] |
| Do you log tokens? | No — tokens are never written to any log |
| Do you share data with third parties? | No — data stays within the coaching organisation |
| Privacy Policy URL | [https://yourdomain.com/privacy] |
| Terms of Service URL | [https://yourdomain.com/terms] |
| Security contact | [security@yourdomain.com] |
| Incident response SLA | [TODO: define and link runbook] |
| Data deletion process | Disconnect removes credentials; full deletion API in progress |
| Rate limiting | Yes — path-scoped throttling in production |
| Webhook verification | Yes — HMAC-signed token, fail-closed if not configured |

We are ready to complete [VENDOR]'s official API access form / security questionnaire at your
convenience. Please send it to [engineering@yourdomain.com] or advise on next steps.

Thank you for your time.

Best regards,
[YOUR NAME]
[TITLE]
[COMPANY LEGAL NAME]
[engineering@yourdomain.com]
[https://yourdomain.com]
