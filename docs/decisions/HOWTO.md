# How to Create an ADR

Manual, lightweight workflow. No automation required.

## When to create an ADR

Create one when you make an architectural decision that:

- Changes a non-negotiable law or its interpretation.
- Commits to (or retires) a vendor, framework, library, or service.
- Sets or changes canonical values (brand tokens, stack components, naming conventions).
- Defers a decision whose re-evaluation requires durable context.
- Resolves a conflict between two sources of truth in the repo.

Do NOT create an ADR for:

- Bug fixes (even load-bearing ones).
- Routine feature work that follows existing patterns.
- Code style / formatting choices (those belong in lint config).
- Decisions that only affect one file in a single session.

## Steps

1. **Find the next number.** Open [README.md](README.md), look at the index, increment by one. ADRs are sequential. No reserved numbers.

2. **Copy the template.** From the repo root:

   ```bash
   cp docs/decisions/TEMPLATE.md docs/decisions/ADR-NNN-short-kebab-title.md
   ```

   Title convention: `ADR-<3-digit-number>-<short-kebab-case-summary>.md`. Keep under 60 chars.

3. **Fill in every field.** If a field does not apply, delete the line (don't leave placeholder text). Required minimum:

   - `Status`
   - `Date`
   - `Decider`
   - `Roadmap phase at decision`
   - `Context`, `Decision`, `Consequences`, `Triggers for Re-evaluation`

4. **Cite evidence.** Every factual claim in `Context` and `Consequences` must reference a file path, commit SHA, or external link. No invented history.

5. **Update the index.** Edit [README.md](README.md) and add a row to the Index table. The row uses the same `Status` and `Outcome` values as the ADR header.

6. **Commit.** One commit per ADR when possible. Commit message format:

   ```
   docs(decisions): add ADR-NNN <short title>
   ```

## Amending or superseding an existing ADR

- **Full replacement** → create a new ADR. Set `Supersedes: ADR-XXX` in the new one. Edit the old ADR to add `Superseded-by: ADR-YYY` and change `Status` to `superseded`.
- **Partial replacement** → create a new ADR. Set `Partially-supersedes: ADR-XXX` in the new one. Edit the old ADR to add `Partially-superseded-by: ADR-YYY`. Leave `Status` as-is.
- **Clause-level amendment** (no replacement) → create a new ADR. Set the scope of the amendment in `Decision`. Edit the old ADR to append the new ADR ID to the `Amended-by` line.

Never rewrite an existing ADR's body after it was merged — add a new ADR instead. ADRs are an append-only log.

## What counts as a "measurable trigger"

Good (measurable):

- `tailwind.config.js` has ≥5 entries in `theme.extend`.
- Claude Design exits research preview to GA with public pricing.
- ≥3 consecutive PRs modify >40% LOC in `frontend/`.

Bad (vague):

- "When we have time."
- "In a few months."
- "When the team grows."

If you can't express the trigger as something a grep or a status check could verify, keep iterating until you can.
