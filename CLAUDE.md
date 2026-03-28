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
- PR-128 ⏳ — Real-side PMC (CTL/ATL/TSB from CompletedActivity)
- PR-129 ⏳ — Historical backfill pipeline
- PR-130 ✅ MERGED — OrganizationSubscription + billing gates (require_plan)
- PR-131 ✅ MERGED — MercadoPago subscriptions + 15-day Pro trial
- PR-132 ✅ MERGED — Billing views: status, subscribe, cancel
- PR-133 ✅ MERGED — CoachPricingPlan + AthleteSubscription models
- PR-134 ✅ MERGED — Coach connects MercadoPago account (MP OAuth via OrgOAuthCredential)
- PR-135 ✅ MERGED — Athlete invitation + MP preapproval creation flow
- PR-136 ✅ MERGED — AthleteSubscription webhook handler (payment status sync)
- PR-147 ✅ MERGED — Smart Alerts + Internal Messaging
- PR-148 ✅ DONE — Real compliance (actual/planned), bulk query, sessions_per_day, streak, weekly pulse, coach briefing
- PR-149 ⏳ NEXT

## After each PR
Update .claude/agent-memory-local/cto/project_roadmap_state.md and commit it with the PR.
