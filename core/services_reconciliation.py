"""
core/services_reconciliation.py

PR-118: Plan vs Real Reconciliation Service

Deterministic, provider-agnostic, multi-tenant-safe reconciliation engine
for Quantoryn / MendietaTrailPlatform.

Domain invariant:
    Reconciliation is an EXPLICIT, AUDITABLE operation.
    - It never mutates PlannedWorkout or CompletedActivity.
    - It operates on normalized domain data only (no provider payloads).
    - Organization scoping is enforced at every query.

Compliance score: 0..120
    100 = planned target exactly met
    <100 = under-compliance
    >100 = over-compliance (hard cap at 120)

Compliance categories (centralized in COMPLIANCE_RANGES):
    not_completed  0–59
    regular        60–84
    completed      85–100
    over_completed 101–120

Signals: structured string constants (ComplianceSignal class), stored as a
JSON list on WorkoutReconciliation.signals for future alert wiring.

Matching: deterministic, confidence-aware, fail-closed on ambiguity.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from django.utils import timezone

from .models import CompletedActivity, WorkoutAssignment, WorkoutReconciliation

logger = logging.getLogger("quantoryn.reconciliation")


# ============================================================================
# Constants — centralized compliance rules
# Single source of truth; do not duplicate these across the codebase.
# ============================================================================

# (min_score_inclusive, max_score_inclusive, category_slug)
COMPLIANCE_RANGES: tuple[tuple[int, int, str], ...] = (
    (0,   59,  "not_completed"),
    (60,  84,  "regular"),
    (85,  100, "completed"),
    (101, 120, "over_completed"),
)

SCORE_MIN: int = 0
SCORE_MAX: int = 120

# Minimum confidence to accept an automatic match (0..1).
# Below this threshold the result is marked UNMATCHED rather than RECONCILED.
AUTO_MATCH_CONFIDENCE_THRESHOLD: float = 0.6

# Default date proximity window for auto-matching (±days around effective_date)
DEFAULT_MATCH_WINDOW_DAYS: int = 1

# Ratio thresholds that trigger secondary signals
SIGNAL_UNDER_THRESHOLD: float = 0.85   # ratio < this → "short" signal
SIGNAL_OVER_THRESHOLD:  float = 1.15   # ratio > this → "long" / "over" signal


# ============================================================================
# Compliance signal constants
# Single source of truth — stored in WorkoutReconciliation.signals as JSON list.
# ============================================================================

class ComplianceSignal:
    """
    Structured compliance signal constants.

    Usage:
        signals.append(ComplianceSignal.DURATION_SHORT)

    Future alerts should filter by these constants; never compare free strings.
    """
    UNDER_COMPLETED          = "under_completed"
    OVER_COMPLETED           = "over_completed"
    DURATION_SHORT           = "duration_short"
    DURATION_LONG            = "duration_long"
    DISTANCE_SHORT           = "distance_short"
    DISTANCE_LONG            = "distance_long"
    ELEVATION_SHORT          = "elevation_short"
    ELEVATION_LONG           = "elevation_long"
    PACE_OUT_OF_TARGET       = "pace_out_of_target"
    HEART_RATE_OUT_OF_TARGET = "heart_rate_out_of_target"   # stub — no HR data yet
    PLANNED_BUT_NOT_EXECUTED = "planned_but_not_executed"
    EXECUTION_WITHOUT_PLAN   = "execution_without_plan"
    POSSIBLE_OVERREACHING    = "possible_overreaching"


# ============================================================================
# Discipline compatibility mapping
# Provider-agnostic: maps TIPO_ACTIVIDAD codes to PlannedWorkout.Discipline slugs.
# This mapping must never contain provider-specific payload fields.
# ============================================================================

_SPORT_TO_DISCIPLINE: dict[str, str] = {
    "RUN":          "run",
    "TRAIL":        "trail",
    "TRAILRUNNING": "trail",   # Strava normalizer variant
    "CYCLING":      "bike",
    "MTB":          "bike",
    "SWIMMING":     "swim",
    "STRENGTH":     "strength",
    "CARDIO":       "other",
    "INDOOR_BIKE":  "bike",
    "REST":         "other",
    "OTHER":        "other",
}

# Run-family disciplines that use effort-based compliance scoring.
_RUN_FAMILY: frozenset[str] = frozenset({"run", "trail"})

# Discipline pairs considered compatible for matching (symmetric).
# run ↔ trail: both are foot-based running variants; may match when discipline
# labeling varies between coach prescription and provider normalization.
_COMPATIBLE_DISCIPLINE_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"run",      "run"}),
    frozenset({"run",      "trail"}),   # foot-based running variants
    frozenset({"trail",    "trail"}),
    frozenset({"bike",     "bike"}),
    frozenset({"swim",     "swim"}),
    frozenset({"strength", "strength"}),
    frozenset({"other",    "other"}),
})


def _disciplines_compatible(plan_discipline: str, activity_sport: str) -> bool:
    """Return True if the planned discipline and activity sport are compatible."""
    activity_discipline = _SPORT_TO_DISCIPLINE.get(activity_sport.upper(), "other")
    return frozenset({plan_discipline, activity_discipline}) in _COMPATIBLE_DISCIPLINE_PAIRS


# ============================================================================
# Result types — pure dataclasses, no ORM state
# ============================================================================

@dataclass
class VariableComplianceDetail:
    """
    Per-variable compliance breakdown for one evaluation axis.

    ratio:  actual / planned for volume variables (duration, distance, elevation).
            planned_pace / actual_pace for pace (inverted: lower pace = faster).
    score:  0..120 contribution from this variable alone.
    """
    planned:  float | None
    actual:   float | None
    ratio:    float | None
    score:    int   | None
    signals:  list[str]

    def as_dict(self) -> dict:
        return {
            "planned": self.planned,
            "actual":  self.actual,
            "ratio":   round(self.ratio, 4) if self.ratio is not None else None,
            "score":   self.score,
            "signals": self.signals,
        }


@dataclass
class ReconciliationScoreResult:
    """Output of score_compliance(). Immutable computation result."""
    score:          int               # 0..120 (clamped headline score)
    category:       str               # compliance category slug
    primary_target: str               # which variable drove the score
    detail:         dict[str, VariableComplianceDetail]
    signals:        list[str]         # deduplicated ordered list


@dataclass
class WeeklyAdherenceResult:
    """Aggregated weekly compliance for one athlete within one organization."""
    week_start:           datetime.date
    week_end:             datetime.date
    organization_id:      int
    athlete_id:           int
    planned_count:        int
    reconciled_count:     int
    missed_count:         int
    unmatched_count:      int
    avg_compliance_score: float | None
    adherence_pct:        float    # reconciled / planned * 100; 0.0 when planned=0


# ============================================================================
# Internal scoring helpers
# ============================================================================

def _classify_compliance(score: int) -> str:
    """Return the compliance category slug for a given score."""
    for lo, hi, category in COMPLIANCE_RANGES:
        if lo <= score <= hi:
            return category
    return "not_completed"


def _clamp_score(raw: float) -> int:
    """Clamp a raw float to the valid 0..120 integer range."""
    return max(SCORE_MIN, min(SCORE_MAX, round(raw)))


def _score_ratio(ratio: float) -> int:
    """Convert a volume ratio (actual/planned) to a 0..120 score."""
    return _clamp_score(ratio * 100)


def _duration_detail(
    planned_s: float | None,
    actual_s:  float | None,
) -> VariableComplianceDetail:
    """Compute compliance detail for session duration."""
    signals: list[str] = []
    if not planned_s or planned_s <= 0:
        return VariableComplianceDetail(
            planned=None, actual=actual_s, ratio=None, score=None, signals=signals
        )
    if actual_s is None or actual_s <= 0:
        return VariableComplianceDetail(
            planned=planned_s, actual=0.0, ratio=0.0, score=0,
            signals=[ComplianceSignal.DURATION_SHORT],
        )
    ratio = actual_s / planned_s
    score = _score_ratio(ratio)
    if ratio < SIGNAL_UNDER_THRESHOLD:
        signals.append(ComplianceSignal.DURATION_SHORT)
    if ratio > SIGNAL_OVER_THRESHOLD:
        signals.append(ComplianceSignal.DURATION_LONG)
    return VariableComplianceDetail(
        planned=planned_s, actual=actual_s, ratio=ratio, score=score, signals=signals
    )


def _distance_detail(
    planned_m: float | None,
    actual_m:  float | None,
) -> VariableComplianceDetail:
    """Compute compliance detail for session distance."""
    signals: list[str] = []
    if not planned_m or planned_m <= 0:
        return VariableComplianceDetail(
            planned=None, actual=actual_m, ratio=None, score=None, signals=signals
        )
    if actual_m is None or actual_m <= 0:
        return VariableComplianceDetail(
            planned=planned_m, actual=0.0, ratio=0.0, score=0,
            signals=[ComplianceSignal.DISTANCE_SHORT],
        )
    ratio = actual_m / planned_m
    score = _score_ratio(ratio)
    if ratio < SIGNAL_UNDER_THRESHOLD:
        signals.append(ComplianceSignal.DISTANCE_SHORT)
    if ratio > SIGNAL_OVER_THRESHOLD:
        signals.append(ComplianceSignal.DISTANCE_LONG)
    return VariableComplianceDetail(
        planned=planned_m, actual=actual_m, ratio=ratio, score=score, signals=signals
    )


def _pace_detail(
    planned_duration_s: float | None,
    planned_distance_m: float | None,
    actual_duration_s:  float | None,
    actual_distance_m:  float | None,
) -> VariableComplianceDetail:
    """
    Compute compliance detail for session pace (s/km).

    Pace is an inverse metric: lower = faster.
    ratio = planned_pace / actual_pace
        ratio > 1 → athlete ran faster than planned (over-compliance for pace)
        ratio < 1 → athlete ran slower than planned (under-compliance for pace)

    Requires both duration and distance to be > 0 for both planned and actual.
    Returns score=None when either side lacks sufficient data.
    """
    signals: list[str] = []
    no_plan = (not planned_duration_s or planned_duration_s <= 0
               or not planned_distance_m or planned_distance_m <= 0)
    no_actual = (not actual_duration_s or actual_duration_s <= 0
                 or not actual_distance_m or actual_distance_m <= 0)

    if no_plan:
        return VariableComplianceDetail(
            planned=None, actual=None, ratio=None, score=None, signals=signals
        )
    if no_actual:
        return VariableComplianceDetail(
            planned=None, actual=None, ratio=None, score=None,
            signals=[ComplianceSignal.PACE_OUT_OF_TARGET],
        )

    planned_pace = planned_duration_s / (planned_distance_m / 1000.0)  # s/km
    actual_pace  = actual_duration_s  / (actual_distance_m  / 1000.0)  # s/km

    # ratio: planned/actual — >1 means athlete was faster than planned
    ratio = planned_pace / actual_pace
    score = _score_ratio(ratio)
    if ratio < SIGNAL_UNDER_THRESHOLD or ratio > SIGNAL_OVER_THRESHOLD:
        signals.append(ComplianceSignal.PACE_OUT_OF_TARGET)
    return VariableComplianceDetail(
        planned=round(planned_pace, 2),
        actual=round(actual_pace, 2),
        ratio=ratio,
        score=score,
        signals=signals,
    )


def _effort_detail(
    planned_distance_m: float | None,
    planned_elevation_m: float | None,
    actual_distance_m: float | None,
    actual_elevation_m: float | None,
) -> VariableComplianceDetail:
    """
    Compute compliance detail using trail-effort formula for run-family disciplines.

    effort = distance_km × (1 + elevation_m / 1000)

    Elevation defaults to 0 when not available (flat-road equivalent).
    Used as primary target for run ↔ trail ↔ trailrunning pairings.
    """
    signals: list[str] = []
    if not planned_distance_m or planned_distance_m <= 0:
        return VariableComplianceDetail(
            planned=None, actual=None, ratio=None, score=None, signals=signals
        )
    plan_elev = max(0.0, float(planned_elevation_m or 0))
    plan_effort = (planned_distance_m / 1000.0) * (1.0 + plan_elev / 1000.0)

    if actual_distance_m is None or actual_distance_m <= 0:
        return VariableComplianceDetail(
            planned=round(plan_effort, 3), actual=0.0, ratio=0.0, score=0,
            signals=[ComplianceSignal.DISTANCE_SHORT],
        )
    real_elev = max(0.0, float(actual_elevation_m or 0))
    real_effort = (actual_distance_m / 1000.0) * (1.0 + real_elev / 1000.0)

    ratio = real_effort / plan_effort
    score = _clamp_score(ratio * 100)
    if ratio < SIGNAL_UNDER_THRESHOLD:
        signals.append(ComplianceSignal.UNDER_COMPLETED)
    if ratio > SIGNAL_OVER_THRESHOLD:
        signals.append(ComplianceSignal.OVER_COMPLETED)
    return VariableComplianceDetail(
        planned=round(plan_effort, 3),
        actual=round(real_effort, 3),
        ratio=round(ratio, 4),
        score=score,
        signals=signals,
    )


def _auto_select_primary_target(assignment: WorkoutAssignment) -> str:
    """
    Determine the dominant evaluation variable.

    Priority:
    1. PlannedWorkout.primary_target_variable if explicitly set.
    2. duration  — if estimated_duration_seconds > 0
    3. distance  — if estimated_distance_meters > 0
    4. pace      — if both duration and distance > 0
    5. duration  — final fallback (score will be 0 if no plan data)
    """
    pw = assignment.planned_workout
    ptv = getattr(pw, "primary_target_variable", "")
    if ptv:
        return ptv
    has_duration = bool(pw.estimated_duration_seconds and pw.estimated_duration_seconds > 0)
    has_distance = bool(pw.estimated_distance_meters and pw.estimated_distance_meters > 0)
    if has_duration:
        return "duration"
    if has_distance:
        return "distance"
    return "duration"  # final fallback


# ============================================================================
# Public API: scoring
# ============================================================================

def score_compliance(
    assignment: WorkoutAssignment,
    activity:   CompletedActivity,
) -> ReconciliationScoreResult:
    """
    Compute a deterministic compliance score (0..120) for an assignment→activity pair.

    PLAN ≠ REAL: This function reads from both sides but NEVER writes to either.
    It returns a pure ReconciliationScoreResult.

    The primary target variable (from PlannedWorkout.primary_target_variable or
    auto-selected) drives the headline score. Secondary variables are evaluated
    and stored in detail for coaching insight. Signals are generated from all
    variables and deduplicated.

    Interval-readiness: the detail dict can be extended in a future PR to include
    block-level or interval-level breakdowns under the key "blocks".
    """
    pw = assignment.planned_workout

    dur  = _duration_detail(
        planned_s=float(pw.estimated_duration_seconds) if pw.estimated_duration_seconds else None,
        actual_s=float(activity.duration_s) if activity.duration_s else None,
    )
    dist = _distance_detail(
        planned_m=float(pw.estimated_distance_meters) if pw.estimated_distance_meters else None,
        actual_m=float(activity.distance_m) if activity.distance_m else None,
    )
    pace = _pace_detail(
        planned_duration_s=float(pw.estimated_duration_seconds) if pw.estimated_duration_seconds else None,
        planned_distance_m=float(pw.estimated_distance_meters) if pw.estimated_distance_meters else None,
        actual_duration_s=float(activity.duration_s) if activity.duration_s else None,
        actual_distance_m=float(activity.distance_m) if activity.distance_m else None,
    )

    detail: dict[str, VariableComplianceDetail] = {
        "duration": dur,
        "distance": dist,
        "pace":     pace,
    }

    # Effort-based scoring for cross-family run pairings (run ↔ trail ↔ trailrunning).
    # Triggered only when plan discipline ≠ activity discipline (both in run family).
    # Effort = distance_km × (1 + elevation_m / 1000) accounts for D+ in trail runs.
    # Same-discipline pairings (run→run, trail→trail) use standard distance/duration scoring.
    plan_discipline     = pw.discipline
    activity_discipline = _SPORT_TO_DISCIPLINE.get(activity.sport.upper(), "other")
    is_run_family       = plan_discipline in _RUN_FAMILY and activity_discipline in _RUN_FAMILY
    is_cross_run_family = is_run_family and plan_discipline != activity_discipline
    has_explicit_target = bool(getattr(pw, "primary_target_variable", ""))
    if is_cross_run_family and pw.estimated_distance_meters:
        effort = _effort_detail(
            planned_distance_m=float(pw.estimated_distance_meters),
            planned_elevation_m=float(pw.elevation_gain_min_m) if pw.elevation_gain_min_m else None,
            actual_distance_m=float(activity.distance_m) if activity.distance_m else None,
            actual_elevation_m=float(activity.elevation_gain_m) if activity.elevation_gain_m else None,
        )
        detail["effort"] = effort

    primary_target = (
        "effort"
        if is_cross_run_family and "effort" in detail and not has_explicit_target
        else _auto_select_primary_target(assignment)
    )
    primary_detail = detail.get(primary_target)

    if primary_detail is None or primary_detail.score is None:
        headline_score = 0
    else:
        headline_score = primary_detail.score

    # Collect signals from all variables
    all_signals: list[str] = []
    for vd in detail.values():
        all_signals.extend(vd.signals)

    # Global signals from headline score
    if headline_score < 85 and ComplianceSignal.UNDER_COMPLETED not in all_signals:
        all_signals.append(ComplianceSignal.UNDER_COMPLETED)
    if headline_score > 100 and ComplianceSignal.OVER_COMPLETED not in all_signals:
        all_signals.append(ComplianceSignal.OVER_COMPLETED)

    # Possible overreaching: duration long AND distance long AND score > 110
    if (
        ComplianceSignal.DURATION_LONG in all_signals
        and ComplianceSignal.DISTANCE_LONG in all_signals
        and headline_score > 110
        and ComplianceSignal.POSSIBLE_OVERREACHING not in all_signals
    ):
        all_signals.append(ComplianceSignal.POSSIBLE_OVERREACHING)

    # Deduplicate preserving first-occurrence order
    seen: set[str] = set()
    deduped: list[str] = []
    for s in all_signals:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    return ReconciliationScoreResult(
        score=headline_score,
        category=_classify_compliance(headline_score),
        primary_target=primary_target,
        detail=detail,
        signals=deduped,
    )


# ============================================================================
# Public API: matching
# ============================================================================

def find_best_match(
    assignment:  WorkoutAssignment,
    window_days: int = DEFAULT_MATCH_WINDOW_DAYS,
) -> tuple[CompletedActivity | None, float, str | None]:
    """
    Find the best matching CompletedActivity for a WorkoutAssignment.

    Returns (activity, confidence, diagnostic_reason):
    - activity:   matched CompletedActivity, or None
    - confidence: 0..1 confidence score
    - reason:     diagnostic string when no match found; None on clean match

    Matching rules (applied in order):
    1. activity.athlete must equal assignment.athlete (uses P1 FK; skips if null)
    2. Date: |activity.start_time.date() - assignment.effective_date| <= window_days
    3. Discipline: must be compatible per _COMPATIBLE_DISCIPLINE_PAIRS
    4. Activity must not already be linked to a RECONCILED reconciliation record

    Fail-closed: if multiple candidates survive filtering → (None, 0.0, "ambiguous")

    Confidence scoring:
    - 1.0: exact date + exact discipline
    - 0.9: exact date + compatible-but-different discipline
    - 0.8: ±1 day   + exact discipline
    - 0.6: ±1 day   + compatible-but-different discipline

    Provider-agnostic: operates on normalized domain fields only.
    """
    athlete = assignment.athlete
    if athlete is None:
        logger.info(
            "reconciliation.match.skip",
            extra={
                "event_name":       "auto_match_skip",
                "reason_code":      "assignment_has_no_athlete_fk",
                "assignment_id":    assignment.pk,
                "organization_id":  assignment.organization_id,
            },
        )
        return None, 0.0, "no_athlete_fk_on_assignment"

    effective_date = assignment.effective_date
    date_lo = effective_date - datetime.timedelta(days=window_days)
    date_hi = effective_date + datetime.timedelta(days=window_days)

    # Candidate activities for this athlete in the date window,
    # excluding those already bound to a different RECONCILED record.
    candidates = (
        CompletedActivity.objects
        .filter(
            athlete=athlete,
            start_time__date__gte=date_lo,
            start_time__date__lte=date_hi,
        )
        .exclude(
            reconciliations__state=WorkoutReconciliation.State.RECONCILED,
        )
        .order_by("start_time")
    )

    plan_discipline = assignment.planned_workout.discipline
    compatible = [
        ca for ca in candidates
        if _disciplines_compatible(plan_discipline, ca.sport)
    ]

    if not compatible:
        return None, 0.0, "no_compatible_activity_in_window"

    if len(compatible) > 1:
        logger.warning(
            "reconciliation.match.ambiguous",
            extra={
                "event_name":       "auto_match_ambiguous",
                "assignment_id":    assignment.pk,
                "organization_id":  assignment.organization_id,
                "candidate_count":  len(compatible),
            },
        )
        return None, 0.0, "ambiguous"

    activity = compatible[0]
    activity_date       = activity.start_time.date()
    activity_discipline = _SPORT_TO_DISCIPLINE.get(activity.sport.upper(), "other")
    exact_date          = activity_date == effective_date
    exact_discipline    = plan_discipline == activity_discipline

    if exact_date and exact_discipline:
        confidence = 1.0
    elif exact_date and not exact_discipline:
        confidence = 0.9
    elif not exact_date and exact_discipline:
        confidence = 0.8
    else:
        confidence = 0.6

    return activity, confidence, None


# ============================================================================
# Public API: reconciliation operations
# ============================================================================

def reconcile(
    *,
    assignment:       WorkoutAssignment,
    activity:         CompletedActivity | None = None,
    method:           str  = WorkoutReconciliation.MatchMethod.MANUAL,
    match_confidence: float | None = None,
    notes:            str  = "",
) -> WorkoutReconciliation:
    """
    Explicitly reconcile a WorkoutAssignment with a CompletedActivity (or mark missed).

    PLAN ≠ REAL: this function never modifies assignment or activity.

    Idempotent: if a WorkoutReconciliation already exists for this assignment,
    it is updated in-place via update_or_create; no duplicate records are created.

    Parameters
    ----------
    assignment : WorkoutAssignment
        The planning record being evaluated.
    activity : CompletedActivity | None
        The matched real activity. Pass None to mark the session as MISSED.
    method : str
        MatchMethod value: "auto", "manual", or "none".
    match_confidence : float | None
        0..1 from automatic matching. Pass None for manual or unmatched.
    notes : str
        Optional diagnostic or coach notes stored on the record.

    Returns
    -------
    WorkoutReconciliation
        The created or updated reconciliation record.
    """
    now = timezone.now()

    if activity is not None:
        result = score_compliance(assignment, activity)
        score_detail_dict = {k: v.as_dict() for k, v in result.detail.items()}

        rec, _ = WorkoutReconciliation.objects.update_or_create(
            assignment=assignment,
            defaults={
                "organization":        assignment.organization,
                "completed_activity":  activity,
                "state":               WorkoutReconciliation.State.RECONCILED,
                "match_method":        method,
                "match_confidence":    match_confidence,
                "compliance_score":    result.score,
                "compliance_category": result.category,
                "primary_target_used": result.primary_target,
                "score_detail":        score_detail_dict,
                "signals":             result.signals,
                "reconciled_at":       now,
                "notes":               notes,
            },
        )
    else:
        # No activity → mark missed
        rec, _ = WorkoutReconciliation.objects.update_or_create(
            assignment=assignment,
            defaults={
                "organization":        assignment.organization,
                "completed_activity":  None,
                "state":               WorkoutReconciliation.State.MISSED,
                "match_method":        WorkoutReconciliation.MatchMethod.NONE,
                "match_confidence":    None,
                "compliance_score":    0,
                "compliance_category": "not_completed",
                "primary_target_used": "",
                "score_detail":        {},
                "signals":             [ComplianceSignal.PLANNED_BUT_NOT_EXECUTED],
                "reconciled_at":       now,
                "notes":               notes or "Marked missed: no activity recorded.",
            },
        )

    logger.info(
        "reconciliation.reconcile",
        extra={
            "event_name":      "reconcile",
            "organization_id": assignment.organization_id,
            "assignment_id":   assignment.pk,
            "activity_id":     activity.pk if activity else None,
            "state":           rec.state,
            "score":           rec.compliance_score,
            "method":          method,
        },
    )
    return rec


def auto_match_and_reconcile(
    *,
    assignment:  WorkoutAssignment,
    window_days: int = DEFAULT_MATCH_WINDOW_DAYS,
) -> WorkoutReconciliation:
    """
    Automatically find the best matching activity and reconcile.

    Confidence-aware, fail-closed on ambiguity:
    - AMBIGUOUS state when multiple candidates exist (no score, coach review needed)
    - UNMATCHED state when no candidate found or confidence < threshold
    - RECONCILED state when exactly one high-confidence match found

    Idempotent: safe to call multiple times on the same assignment.
    """
    now = timezone.now()
    activity, confidence, reason = find_best_match(assignment, window_days=window_days)

    if reason == "ambiguous":
        rec, _ = WorkoutReconciliation.objects.update_or_create(
            assignment=assignment,
            defaults={
                "organization":        assignment.organization,
                "completed_activity":  None,
                "state":               WorkoutReconciliation.State.AMBIGUOUS,
                "match_method":        WorkoutReconciliation.MatchMethod.NONE,
                "match_confidence":    None,
                "compliance_score":    None,
                "compliance_category": "",
                "primary_target_used": "",
                "score_detail":        {},
                "signals":             [],
                "reconciled_at":       None,
                "notes":               "Automatic match found multiple candidates; coach review required.",
            },
        )
        logger.warning(
            "reconciliation.ambiguous",
            extra={
                "event_name":      "auto_match_ambiguous",
                "organization_id": assignment.organization_id,
                "assignment_id":   assignment.pk,
            },
        )
        return rec

    if activity is None or confidence < AUTO_MATCH_CONFIDENCE_THRESHOLD:
        rec, _ = WorkoutReconciliation.objects.update_or_create(
            assignment=assignment,
            defaults={
                "organization":        assignment.organization,
                "completed_activity":  None,
                "state":               WorkoutReconciliation.State.UNMATCHED,
                "match_method":        WorkoutReconciliation.MatchMethod.NONE,
                "match_confidence":    confidence if confidence else None,
                "compliance_score":    None,
                "compliance_category": "",
                "primary_target_used": "",
                "score_detail":        {},
                "signals":             [],
                "reconciled_at":       None,
                "notes":               f"Auto-match: {reason or 'low_confidence'}.",
            },
        )
        return rec

    return reconcile(
        assignment=assignment,
        activity=activity,
        method=WorkoutReconciliation.MatchMethod.AUTO,
        match_confidence=confidence,
    )


def mark_assignment_missed(
    *,
    assignment: WorkoutAssignment,
    notes:      str = "",
) -> WorkoutReconciliation:
    """
    Mark an assignment as MISSED (no activity recorded after effective_date passed).

    Idempotent: safe to call multiple times.
    Does not validate whether the date has actually passed — caller is responsible
    for date-gating logic in any batch process.
    """
    return reconcile(
        assignment=assignment,
        activity=None,
        method=WorkoutReconciliation.MatchMethod.NONE,
        notes=notes or "Marked missed: no activity recorded.",
    )


# ============================================================================
# Public API: weekly adherence aggregation
# ============================================================================

def compute_weekly_adherence(
    *,
    organization,
    athlete,
    week_start: datetime.date,
) -> WeeklyAdherenceResult:
    """
    Aggregate Plan vs Real compliance for one athlete within one calendar week.

    Week range: [week_start, week_start + 6 days] (7 days, inclusive).

    Counts WorkoutReconciliation records whose assignment.scheduled_date falls
    in the week. Assignments without any reconciliation record are NOT counted
    here — they represent a planning gap, not an execution gap.

    avg_compliance_score excludes records with null score (unmatched/ambiguous).
    adherence_pct = reconciled_count / planned_count * 100; 0.0 when planned=0.

    Future extension: load-based adherence (TSS-weighted) can be added as an
    additional field without changing this function's signature.

    Returns a WeeklyAdherenceResult dataclass.
    """
    week_end = week_start + datetime.timedelta(days=6)

    records = WorkoutReconciliation.objects.filter(
        organization=organization,
        assignment__athlete=athlete,
        assignment__scheduled_date__gte=week_start,
        assignment__scheduled_date__lte=week_end,
    ).select_related("assignment")

    planned_count    = records.count()
    reconciled_recs  = records.filter(state=WorkoutReconciliation.State.RECONCILED)
    reconciled_count = reconciled_recs.count()
    missed_count     = records.filter(state=WorkoutReconciliation.State.MISSED).count()
    unmatched_count  = records.filter(state=WorkoutReconciliation.State.UNMATCHED).count()

    scores = [r.compliance_score for r in reconciled_recs if r.compliance_score is not None]
    avg_score = (sum(scores) / len(scores)) if scores else None

    adherence_pct = (reconciled_count / planned_count * 100.0) if planned_count > 0 else 0.0

    return WeeklyAdherenceResult(
        week_start=week_start,
        week_end=week_end,
        organization_id=organization.pk,
        athlete_id=athlete.pk,
        planned_count=planned_count,
        reconciled_count=reconciled_count,
        missed_count=missed_count,
        unmatched_count=unmatched_count,
        avg_compliance_score=round(avg_score, 2) if avg_score is not None else None,
        adherence_pct=round(adherence_pct, 2),
    )
