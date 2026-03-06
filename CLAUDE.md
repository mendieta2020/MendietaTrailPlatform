# Claude Code Bootloader — MendietaTrailPlatform / Quantoryn

## Read This First. Then Stop.

Before writing any code, opening any file speculatively, or proposing any plan:

1. **Read `docs/ai/CONSTITUTION.md`** — identity, phase, laws, PR rules, fail conditions.
2. **Read `docs/ai/REPO_MAP.md`** — architecture map, sensitive zones, allowlist guidance.
3. **Read the relevant task capsule in `docs/ai/tasks/`** — if a capsule exists for the task, it defines the allowlist, blast radius, implementation plan, and test plan. Follow it.

Do not scan the repository. Do not open files speculatively. Do not proceed without context.

---

## Current Phase: P0 — Reliability / Vendor-Grade Hardening

This repository is in pre-launch hardening mode. Every change must protect stability, not introduce new surface area. When in doubt, choose the smaller, safer option.

---

## Non-Negotiables (Summary)

| Rule | Short form |
|------|-----------|
| Multi-tenant, fail-closed | Every query is org-scoped. No org = deny. No exceptions. |
| Plan ≠ Real | `PlannedWorkout` and `CompletedActivity` are never merged implicitly. |
| Provider boundary | Provider logic lives only in `integrations/`. Domain code is provider-agnostic. |
| CI must stay green | A PR is not done until all CI checks pass. Never suppress a failing test. |
| No broad refactors | Do not refactor unrelated code. One PR = one idea. ≤ 500 LOC default. |

---

## Context Budget (Hard Limits)

- Open **at most 3 files** before proposing a plan.
- If you need more context, state which single file you need and why — then wait.
- If a task capsule exists, work **only within its allowlist**.
- If a required change falls outside the allowlist or task scope, **stop and ask permission**.
- Never scan the full repository. Use `docs/ai/REPO_MAP.md` to orient.

---

## Standard Operating Sequence

For every non-trivial task, follow this sequence in order:

```
1. Read context files (CONSTITUTION → REPO_MAP → task capsule)
2. Classify the task: Phase (P0/P1/P2) + Risk (Low/Med/High)
3. Identify blast radius: tenancy / OAuth / integrations / CI / prod config
4. Propose a minimal plan (list files, describe change, state what is excluded)
5. Wait for approval before implementing
6. Run tests: python manage.py check → pytest -q → npm run lint → npm run build
7. Report rollback strategy before marking Done
```

---

## Fail Immediately If

- Tenancy leak detected
- OAuth regression risk without protective tests
- Provider logic placed outside `integrations/`
- Secrets in logs or source
- CI left red
- Production security posture weakened

---

*Full rules → `docs/ai/CONSTITUTION.md`*
*Architecture map → `docs/ai/REPO_MAP.md`*
*Task capsules → `docs/ai/tasks/`*
