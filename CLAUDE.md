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
- PR-125 through PR-156 MERGED (see project_roadmap_state.md for full history)
- PR-154 ✅ MERGED — Reporte automático compartible (athlete report with WhatsApp sharing)
- PR-155 ✅ MERGED — Limpieza del edificio (consolidar sidebar, eliminar duplicación)
- PR-156 ✅ MERGED — Mi Progreso del Atleta: Readiness hero + Goals + Weekly + PMC humano + Wellness
- PR-157 ✅ MERGED — Auto-Periodización + Badge Calendario + Timeline Atleta + Historial Planificador
- PR-158 ✅ MERGED — Planificador Pro: Historial Visual + Copiar Semana + Carga Estimada + Plan vs Real
- PR-159 ✅ MERGED — Sidebar Colapsable + Athlete Card (5 Tabs) + GroupPlanning Navigation + Editar Sesión
- PR-160 ✅ MERGED — Fixes funcionales + Calendar Pro + Diferenciación roles + Goal badge
- PR-161 ✅ MERGED — Body Map Pro + Fixes funcionales + Sync coach↔atleta + Ubicación→Clima
- PR-162 THIS PR — Production Ready: Security fix + Saves rotos + Onboarding polish

## PR Protocol (PASO 0)
Before writing any code for a new PR:
1. Create a feature branch from latest main
2. All changes on the feature branch only
3. Never commit directly to main

## After each PR
Update .claude/agent-memory-local/cto/project_roadmap_state.md and commit it with the PR.

## Deferred Decisions
- [ADR-001 — Claude Design adoption diferida](docs/decisions/ADR-001-claude-design-deferred.md) (2026-04-21): no adoptar en P2. Re-evaluar cuando se cumplan los triggers medibles del ADR.
