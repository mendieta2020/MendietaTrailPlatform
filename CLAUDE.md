Architecture Overview & Routing: See @docs/ai/REPO_MAP.md
Non-Negotiable Engineering Laws: See @docs/ai/CONSTITUTION.md
Always adhere to the current phase restrictions (vendor-grade reliability).
Run the /quantoryn-review skill when evaluating high-risk changes.

## Dual-Agent Workflow

Two agents operate this repo with distinct roles:

**Antigravity (Claude Code — terminal)**
- Role: Fabrication. The ONLY agent that writes, edits, commits, and opens PRs.
- Reads files, runs tests, generates migrations, pushes branches.
- Receives precise prompts from the Lab before starting each PR.
- Never starts a PR without a prompt from the Lab.

**Lab (Claude Chat — browser)**
- Role: Strategy. Never writes code directly.
- Designs prompts for each PR with full context.
- Maintains roadmap, diagnoses failures, prepares next PR while current one runs.
- Receives terminal output (text only) to diagnose errors.

## Current Phase: P2 — Historical Data, Analytics & Billing

PR queue:
- PR-125 through PR-180 ✅ MERGED (see `.claude/agent-memory-local/cto/project_roadmap_state.md` for full history)
- No PR in flight as of 2026-04-22

### Next queue (confirmed order — "paint after plumbing")
1. **PR-181** — Weather enrichment (Bug #23): populate `weather_snapshot` in `/calendar-timeline/` (OWM Case A window ±4d).
2. **PR-182** — Residual bug bundle: Bug #29 (notification "Ver sesión" nav), Bug #30 (drawer 41min vs modal 165.9min data inconsistency), Bug #32 (intensity graph flat on "personalizado" workouts), Bug #27 (TRAIL↔RUNNING pairing now unblocked after PR-180).
3. **PR-179c** — Design system: card unification, grid alignment, calendar auto-scroll, coach single-modal (replaces modal+drawer), coach-first landing.

### Future PRs (non-blocking, triaged)
- Bug #33: `Alumno.entrenador_id` upstream persistence fix (PR-180 added resilience, not root-cause).
- Bug #35: reconnect kicks user out of athlete/coach panel context.
- Bug #37: consolidate `_derive_org_from_alumno` vs `_derive_organization` (tech debt).
- Bug #38: SocialAccount lookup outside `select_for_update` atomic block (perf).
- Branding bundle: photos on R2 + branded emails (all 4 decisions resolved, DNS ready).

## PR Protocol (PASO 0)
Before writing any code for a new PR:
1. Create a feature branch from latest main
2. All changes on the feature branch only
3. Never commit directly to main

## After each PR
Update .claude/agent-memory-local/cto/project_roadmap_state.md and commit it with the PR.

## Deferred Decisions
- [ADR-001 — Claude Design adoption diferida](docs/decisions/ADR-001-claude-design-deferred.md) (2026-04-21): no adoptar en P2. Re-evaluar cuando se cumplan los triggers medibles del ADR.
