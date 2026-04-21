# ADR-002 — Ratify Teal (#00D4AA) as Canonical Quantoryn Brand

- **Status:** accepted
- **Date:** 2026-04-21
- **Decider:** Fernando Mendieta (CTO)
- **Technical author:** Antigravity (Claude Code)
- **Roadmap phase at decision:** P2 — Historical Data, Analytics & Billing
- **Related skills:** `quantoryn-frontend-ux` (global, out-of-repo — requires manual update; see Implementation Plan)

---

## Context

Evidence gathered in this worktree on 2026-04-21 revealed a **conflict between two sources of truth** about the Quantoryn CTA / brand color:

| Source | Value | File:line |
|--------|-------|-----------|
| Product code (CSS tokens) | **Teal `#00D4AA`** as `--brand-primary` and `--btn-primary-bg` | `frontend/src/styles/tokens.css:3,25` |
| Product code (MUI theme) | **Teal `#00D4AA`** as `palette.primary.main` | `frontend/src/theme/theme.js:7` |
| UX governance skill | **Amber `bg-amber-500`** as primary CTA | `~/.claude/skills/quantoryn-frontend-ux/SKILL.md:21,30,97,114,137,142` (6 occurrences) |

The skill explicitly forbids alternatives: *"Nunca azul genérico para CTAs primarios"* (line 21). The product code, by contrast, ships teal to production.

No occurrences of `FF6B35`, `Bebas Neue`, or `DM Sans` were found in the repo. An earlier working hypothesis that a separate "MTT" brand (coral + Bebas Neue + DM Sans) might coexist was discarded: it was a visual artifact from memory, not a verifiable state in this repo.

This ADR resolves the conflict.

---

## Decision

**Teal `#00D4AA` is ratified as the canonical Quantoryn brand color.** It governs:

- Primary CTAs (buttons, submit actions, empty-state call-to-actions).
- Input focus rings.
- Active navigation states (sidebar, tabs).
- Brand marks wherever they appear.

Companion tokens already defined in `frontend/src/styles/tokens.css` stand as canonical:

- `--brand-primary: #00D4AA`
- `--brand-primary-hover: #00BF99`
- `--btn-primary-bg: #00D4AA`
- `--btn-primary-text: #0D1117` (dark text on teal surface)
- `--btn-primary-hover: #00BF99`

**Amber is retired as a brand value.** Any future amber usage must be documented as a non-brand accent (e.g., warning state) in a follow-up design-system doc.

**Scope boundary:** this ADR governs the MTP / Quantoryn product repo only. It does not make claims about any separate MTT marketing property.

---

## Alternatives Considered

- **Ratify amber as canonical.** Rejected: would require rewriting `tokens.css`, `theme.js`, and any rendered surface currently shipping teal — blast radius extends into production. The skill is easier to align to the code than the code to the skill.
- **Keep both (amber in marketing surfaces, teal in product).** Rejected: no marketing surface exists in this repo, and dual-brand without enforcement produces drift. Re-open only if a marketing subdirectory is introduced.
- **Defer the decision.** Rejected: the conflict is already causing confusion for agents interpreting the skill as authoritative (including this one, in a prior session turn). Leaving it open costs more than resolving now.

---

## Consequences

### Positive
- Single source of truth for brand color across code and governance.
- Prepares ground for future consolidation: `tokens.css` → `tailwind.config.extend` → `theme.js` derived (see [ADR-001](ADR-001-claude-design-deferred.md) trigger #1).
- Unblocks `brand-guidelines.md` authorship whenever Fernando decides to add it.

### Negative / Trade-offs
- The `quantoryn-frontend-ux` skill lives **outside this repo** (`~/.claude/skills/`). It cannot be updated via a PR. Fernando must apply the diff below manually after merge.
- Until the skill is updated, agents auto-invoking `quantoryn-frontend-ux` will still propose amber CTAs. This ADR should be linked prominently from the skill's `description` frontmatter in the follow-up update to reduce confusion.

### Neutral / Follow-ups
- `brand-guidelines.md` is out of scope for this ADR — authored in a separate PR.
- Wiring `tailwind.config.extend.colors` to consume `tokens.css` CSS variables is out of scope — already listed as preparatory work in ADR-001.

---

## Triggers for Re-evaluation

1. A marketing property or second brand surface is introduced into this repo (e.g., `marketing/` directory or a separate landing repo consolidates here).
2. Design system consolidation (ADR-001 trigger #1) produces a new canonical color during migration.
3. Accessibility audit fails for teal contrast on a critical surface — forces re-opening the palette decision.

---

## Implementation Plan

This ADR is **documentation-only**. No production code is modified by the PR that introduces it.

**Manual skill update required** (out-of-repo, to be applied by Fernando after this PR merges):

File: `~/.claude/skills/quantoryn-frontend-ux/SKILL.md`

The 6 amber references below must be replaced. The recommended replacement uses CSS variables from `tokens.css` as the single source of truth (Option A). Direct hex (Option B) or wired Tailwind tokens (Option C) are acceptable alternatives once `tailwind.config.extend` is populated.

### Line 21

```diff
-- **Acción principal (CTA):** botones en Naranja/Amber — `bg-amber-500 hover:bg-amber-600 text-white`. Nunca azul genérico para CTAs primarios.
+- **Acción principal (CTA):** botones en Teal Quantoryn — `bg-[var(--btn-primary-bg)] hover:bg-[var(--btn-primary-hover)] text-[var(--btn-primary-text)]` (canonical teal `#00D4AA`, defined in `frontend/src/styles/tokens.css`). Nunca azul ni amber para CTAs primarios.
```

### Line 30

```diff
-- Inputs: `rounded-lg border border-slate-300 focus:ring-2 focus:ring-amber-500 focus:border-amber-500`.
+- Inputs: `rounded-lg border border-slate-300 focus:ring-2 focus:ring-[var(--login-input-focus)] focus:border-[var(--login-input-focus)]` (teal focus ring, `#00D4AA`).
```

### Line 97

```diff
-4. **Botón CTA** que inicia la acción primaria — color Amber, label en positivo ("Crear primer atleta", "Agregar entrenamiento").
+4. **Botón CTA** que inicia la acción primaria — color Teal Quantoryn (`--btn-primary-bg`), label en positivo ("Crear primer atleta", "Agregar entrenamiento").
```

### Line 114

```diff
-        className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition-colors"
+        className="px-4 py-2 bg-[var(--btn-primary-bg)] hover:bg-[var(--btn-primary-hover)] text-[var(--btn-primary-text)] text-sm font-medium rounded-lg transition-colors"
```

### Line 137

```diff
-- [ ] ¿El CTA primario es Amber, no azul?
+- [ ] ¿El CTA primario es Teal (`--btn-primary-bg`), no amber ni azul?
```

### Line 142

```diff
-- [ ] ¿Los inputs tienen `focus:ring-amber-500`?
+- [ ] ¿Los inputs tienen `focus:ring-[var(--login-input-focus)]` (teal)?
```

After applying, add a short note under the skill's frontmatter (or in Ley 1) linking to this ADR:

```markdown
> Brand tokens ratified by [ADR-002](../../docs/decisions/ADR-002-teal-canonical-brand.md) — teal `#00D4AA` is canonical. Amber is retired as a brand value.
```

---

## Rollback

If teal is proven wrong as a brand choice (e.g., the accessibility trigger fires), rollback is: create ADR-00X with `Supersedes: ADR-002`, state the new canonical color, and reverse the token values in `tokens.css` and `theme.js` in the same PR. The skill follows the new ADR.

---

## References

- [ADR-001 — Claude Design adoption deferred](ADR-001-claude-design-deferred.md) (2026-04-21) — originally surfaced the brand fragmentation.
- `frontend/src/styles/tokens.css:3,25` — teal tokens.
- `frontend/src/theme/theme.js:7` — MUI palette primary.
- `~/.claude/skills/quantoryn-frontend-ux/SKILL.md:21,30,97,114,137,142` — amber references (out of repo).
- `docs/ai/CONSTITUTION.md` — v4.2 CORE.
