# Architecture Decision Records

This directory records architectural decisions for MendietaTrailPlatform / Quantoryn using a lightweight [MADR](https://adr.github.io/madr/) variant.

## Workflow

- Read [HOWTO.md](HOWTO.md) before creating a new ADR.
- Copy [TEMPLATE.md](TEMPLATE.md) and fill it in. Do not skip fields silently.
- Numbering is sequential (`ADR-001`, `ADR-002`, ...). Do not reserve numbers.
- Every merged ADR must appear in the index below.

## Index

| ID | Title | Status | Outcome | Date |
|----|-------|--------|---------|------|
| [ADR-001](ADR-001-claude-design-deferred.md) | Claude Design adoption | accepted | deferred | 2026-04-21 |
| [ADR-002](ADR-002-teal-canonical-brand.md) | Ratify teal as canonical Quantoryn brand | accepted | — | 2026-04-21 |
| [ADR-003](ADR-003-railway-env-vars-references.md) | Railway internal env vars must be dynamic references | accepted | — | 2026-04-22 |
| [ADR-004](ADR-004-compliance-single-source-of-truth.md) | Compliance: backend single source of truth (cap 150 %) | accepted | — | 2026-04-26 |
| [ADR-005](ADR-005-alumno-athlete-duality-resolution.md) | Alumno/Athlete duality resolution strategy | accepted | partial | 2026-04-26 |

## Conventions

- One ADR = one architectural decision. Multiple decisions in one file = split.
- Status values: `proposed`, `accepted`, `rejected`, `deprecated`, `superseded`.
- Use `amended-by` when a later ADR modifies clauses without fully replacing.
- Use `partially-superseded-by` when a later ADR replaces some clauses but not all.
- Re-evaluation triggers must be **measurable conditions**, never calendar dates.
