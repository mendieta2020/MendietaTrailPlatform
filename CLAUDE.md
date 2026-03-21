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
- PR-125 ✅ MERGED — Athlete.clean() cross-org validation
- PR-126 ✅ MERGED — CompletedActivity.organization FK → Organization
- PR-127 ✅ MERGED — Ingestion fills CompletedActivity.athlete FK
- PR-128 ⏳ NEXT — Real-side PMC (CTL/ATL/TSB from CompletedActivity)
- PR-129 ⏳ — Historical backfill pipeline
- PR-130+ ⏳ — Billing + multi-provider rollout

## After each PR
Update .claude/agent-memory-local/cto/project_roadmap_state.md and commit it with the PR.
