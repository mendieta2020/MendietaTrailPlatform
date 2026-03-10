# Plan vs Real Reconciliation — Domain Documentation
> **Quantoryn / MendietaTrailPlatform**
> Introduced in PR-118. Scientific brainstem of the coaching loop.
> **Last updated:** 2026-03-09

---

## What PR-118 Introduces

PR-118 adds the deterministic Plan vs Real reconciliation foundation:

| Component | Location | Purpose |
|---|---|---|
| `WorkoutReconciliation` model | `core/models.py` | Explicit bridge between plan and real |
| `primary_target_variable` field | `PlannedWorkout` | Dominant evaluation axis per session |
| `services_reconciliation.py` | `core/` | Scoring engine, matching, aggregation |
| Migration `0073_reconciliation` | `core/migrations/` | Schema |
| `tests_reconciliation.py` | `core/` | 45 tests across all scenarios |

---

## Why Plan ≠ Real Must Remain Separate

`PlannedWorkout` represents **scientific intent**: what the coach prescribed.
`CompletedActivity` represents **physiological reality**: what the athlete did.

These two domains must never be merged, because:

1. **Scientific validity**: mixing intent and outcome corrupts both datasets.
2. **Auditability**: coaches must be able to see the original prescription unchanged, even months later.
3. **Re-reconciliation**: if a provider updates an activity (e.g., GPS correction), the plan is unchanged and the reconciliation can be re-run.
4. **Multi-plan scenarios**: one athlete may have multiple planned sessions per day; each assignment must be evaluated independently.

`WorkoutReconciliation` is the **explicit, auditable bridge** — it reads both sides and writes to neither.

---

## Domain Concepts

### WorkoutReconciliation

One record per `WorkoutAssignment` (enforced by OneToOneField). The `completed_activity` FK is nullable — null means the session was missed, unmatched, or is still pending.

```
WorkoutAssignment (plan)  ←  WorkoutReconciliation  →  CompletedActivity (real)
     ↑                              ↑                          ↑
  immutable               explicit comparison             immutable
  prescription            auditable record               ledger entry
```

### State Machine

| State | Meaning |
|---|---|
| `pending` | Initial state. Auto-matching not yet attempted. |
| `reconciled` | One activity matched with sufficient confidence. Score computed. |
| `unmatched` | No candidate activity found in the matching window. |
| `missed` | Effective date passed. No activity ever recorded. Score = 0. |
| `ambiguous` | Multiple candidates found. Fail-closed. Coach review required. |
| `error` | Matching or scoring raised an unexpected exception. |

### Matching Method

| Method | Meaning |
|---|---|
| `auto` | System matched using `find_best_match()` |
| `manual` | Coach/admin explicitly linked plan to activity (future PR) |
| `none` | No activity linked |

---

## Compliance Score: 0..120

The compliance score measures whether the athlete executed the prescribed physiological stimulus.

| Score | Meaning |
|---|---|
| 100 | Planned target exactly met |
| < 100 | Under-compliance |
| > 100 | Over-compliance (athlete exceeded plan) |
| 0 | No execution data |
| 120 | Hard cap (maximum; over-compliance ceiling) |

**Why 120 and not 100?** Because exceeding the plan is a real phenomenon that must be represented — but more is NOT automatically better. Over-compliance may indicate misalignment with coach intent, athlete disobedience, under-prescription, or short-term injury/fatigue risk.

### Compliance Categories

Derived deterministically from score using `COMPLIANCE_RANGES` in `services_reconciliation.py`:

| Category | Score Range | Meaning |
|---|---|---|
| `not_completed` | 0–59 | Significantly under plan |
| `regular` | 60–84 | Partial compliance |
| `completed` | 85–100 | Within planned range |
| `over_completed` | 101–120 | Athlete exceeded the prescription |

These ranges are the single source of truth. Do not hardcode them outside `services_reconciliation.py`.

---

## Primary Target Variable

Each planned session should be evaluated primarily by ONE dominant variable — not all equally. A trail climbing session is evaluated primarily by duration/elevation, not pace. A tempo run is evaluated primarily by pace.

Set on `PlannedWorkout.primary_target_variable` (CharField with choices):

| Value | When to use |
|---|---|
| `duration` | Aerobic base, long runs, recovery (default when duration > 0) |
| `distance` | Volume-focused sessions |
| `elevation_gain` | Mountain/trail sessions (future — requires target elevation field) |
| `pace` | Tempo, threshold, intervals |
| `hr_zone` | HR-controlled sessions (future — requires HR data in CompletedActivity) |

If left blank, the engine auto-selects: `duration` → `distance` → `pace` (in priority order, based on available plan data).

---

## Signals

Structured compliance signals stored as a JSON list on `WorkoutReconciliation.signals`.

| Signal | Meaning |
|---|---|
| `under_completed` | Headline score < 85 |
| `over_completed` | Headline score > 100 |
| `duration_short` | Actual duration < 85% of planned |
| `duration_long` | Actual duration > 115% of planned |
| `distance_short` | Actual distance < 85% of planned |
| `distance_long` | Actual distance > 115% of planned |
| `elevation_short` | Actual elevation < 85% of planned (future) |
| `elevation_long` | Actual elevation > 115% of planned (future) |
| `pace_out_of_target` | Pace ratio outside 85–115% of planned pace |
| `heart_rate_out_of_target` | HR outside target zone (future — stub) |
| `planned_but_not_executed` | Assignment has no linked activity (MISSED state) |
| `execution_without_plan` | Activity arrived with no matching assignment |
| `possible_overreaching` | duration_long + distance_long + score > 110 |

Signals are the future wiring point for alerts, coach dashboards, and AI assistance. Never compare free strings — always use `ComplianceSignal` constants from `services_reconciliation.py`.

---

## score_detail: Per-Variable Breakdown

`WorkoutReconciliation.score_detail` stores the full per-variable computation as JSON:

```json
{
  "duration": {
    "planned": 3600.0,
    "actual":  3420.0,
    "ratio":   0.95,
    "score":   95,
    "signals": []
  },
  "distance": {
    "planned": 10000.0,
    "actual":  9500.0,
    "ratio":   0.95,
    "score":   95,
    "signals": []
  },
  "pace": {
    "planned": 360.0,
    "actual":  360.0,
    "ratio":   1.0,
    "score":   100,
    "signals": []
  }
}
```

This structure is **interval-ready**: future block-level or interval-level detail can be appended as `{"blocks": [...]}` without a schema migration.

---

## Matching Logic

`find_best_match(assignment, window_days=1)` applies rules in order:

1. `activity.athlete` must equal `assignment.athlete` (P1 FK; skips if null)
2. Date: `|activity.start_time.date() - assignment.effective_date| ≤ window_days`
3. Discipline compatibility (foot-based variants: run ↔ trail)
4. Activity must not already be linked to another RECONCILED record

**Confidence scoring:**

| Date | Discipline | Confidence |
|---|---|---|
| Exact | Exact | 1.0 |
| Exact | Compatible | 0.9 |
| ±1 day | Exact | 0.8 |
| ±1 day | Compatible | 0.6 |

**Fail-closed:** multiple candidates → `AMBIGUOUS` state, no score assigned, coach review required.

**Minimum confidence:** `AUTO_MATCH_CONFIDENCE_THRESHOLD = 0.6`. Below this, state = `UNMATCHED`.

---

## Weekly Adherence

`compute_weekly_adherence(organization, athlete, week_start)` returns a `WeeklyAdherenceResult` with:

- `planned_count` — reconciliation records in the week
- `reconciled_count` — RECONCILED state count
- `missed_count` — MISSED state count
- `unmatched_count` — UNMATCHED state count
- `avg_compliance_score` — average of non-null scores (RECONCILED only)
- `adherence_pct` — `reconciled / planned * 100`

**Note:** Assignments without a reconciliation record are not counted (planning gap, not execution gap). Use `WorkoutAssignment` queries separately to find unreconciled assignments.

---

## Service API Reference

```python
from core.services_reconciliation import (
    score_compliance,           # Pure scoring: returns ReconciliationScoreResult
    find_best_match,            # Returns (activity, confidence, reason)
    reconcile,                  # Explicit: activity | None → WorkoutReconciliation
    auto_match_and_reconcile,   # Auto: match + score → WorkoutReconciliation
    mark_assignment_missed,     # Force MISSED state
    compute_weekly_adherence,   # Returns WeeklyAdherenceResult
)
```

All functions are **idempotent** (safe to call multiple times on the same assignment) and **pure read on plan/real data** (never mutate PlannedWorkout or CompletedActivity).

---

## Extension Path: Interval Reconciliation

PR-118 establishes session-level reconciliation only. The architecture is ready for future interval-level reconciliation:

1. `score_detail` already accepts a `"blocks"` key without schema changes
2. `WorkoutBlock` and `WorkoutInterval` are available in the planning domain
3. When `CompletedActivity` gains time-series lap data (future provider normalization), interval scoring can be added as a new function in `services_reconciliation.py` without touching existing logic

**Rule:** Do not add interval parsing until the normalized execution-side data is reliably available from providers.

---

## Extension Path: Manual Coach Override

`WorkoutReconciliation.notes` and `match_method = "manual"` are the extension points for a future UI where coaches can:
- Override an auto-match to link a different activity
- Mark a session as completed with a different activity
- Add coaching context to a reconciliation outcome

This is explicitly not in PR-118 scope.

---

## Known Limitations (as of PR-118)

| Limitation | Tracking | Mitigation |
|---|---|---|
| `CompletedActivity.organization` → User (not Organization) | D2 debt | Matching uses athlete FK, not org FK, on activity side |
| `CompletedActivity.athlete` nullable (pre-PR-114 rows) | D2 backfill | Service skips matching gracefully when athlete=None |
| No HR zone data in CompletedActivity | Future | `hr_zone` target and `HEART_RATE_OUT_OF_TARGET` signal stubbed |
| No elevation target in PlannedWorkout | Future | `elevation_gain` scoring requires a `target_elevation_gain_m` field (separate PR) |
| No interval-level reconciliation | PR-119+ | Architecture is ready; data is not |
| No coach override UI | PR-119+ | `notes` and `match_method="manual"` prepared |

---

*See also: `docs/ai/CONSTITUTION.md`, `docs/ai/REPO_MAP.md`, `docs/ai/playbooks/EXECUTION-BASELINE-PR101-PR120.md`*
