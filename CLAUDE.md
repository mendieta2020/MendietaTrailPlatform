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
- PR-125 through PR-155 MERGED (see project_roadmap_state.md for full history)
- PR-149 ✅ MERGED — Security Sweep (tenancy disambiguation in billing/PMC)
- PR-150 ✅ MERGED — Close Strava ingestion loop (dual-write CompletedActivity)
- PR-151 ✅ MERGED — Dashboard Nivel 1 (team semaphore + ACWR + real CTL in Athletes.jsx)
- PR-152 ✅ MERGED — Vista atleta enriquecida: 7 KPI cards + Readiness Score + metric filters + tooltips
- PR-153 ✅ MERGED — GAP + Ramp Rate + CTL Projection + Volume enhancements
- PR-154 ✅ MERGED — Reporte automático compartible (athlete report with WhatsApp sharing)
- PR-155 ✅ MERGED — Limpieza del edificio (consolidar sidebar, eliminar duplicación)
- PR-156 THIS PR — Mi Progreso del Atleta: Readiness hero + Goals + Weekly + PMC humano + Wellness
- PR-157 NEXT — Diferenciación vista coach vs atleta (roles)

## PR Protocol (PASO 0)
Before writing any code for a new PR:
1. Create a feature branch from latest main
2. All changes on the feature branch only
3. Never commit directly to main

## After each PR
Update .claude/agent-memory-local/cto/project_roadmap_state.md and commit it with the PR.
