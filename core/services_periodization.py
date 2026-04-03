"""
core/services_periodization.py — PR-157

Auto-periodization service: generates TrainingWeek records backward from
an athlete's active race goals.

Design principles:
- Idempotent: uses update_or_create — safe to rerun.
- Fail-closed: never overwrites phase="lesion".
- Organization-scoped: organization FK is always explicit.
- No import from integrations/ — domain-only service.
"""

import datetime
import logging

from core.models import Athlete, AthleteGoal, TrainingWeek

logger = logging.getLogger(__name__)


# ── Cycle pattern helpers ──────────────────────────────────────────────────────

VALID_PATTERNS = ("1:1", "2:1", "3:1", "4:1")


def suggest_cycle_pattern(target_distance_km: float | None) -> str:
    """
    Return the recommended cycle pattern string based on race distance.

    Thresholds (science-based):
    - 0–15 km:   "1:1"  (beginner / short distances)
    - 15–30 km:  "2:1"  (intermediate, half-marathon)
    - 30–80 km:  "3:1"  (advanced, marathon / ultra)
    - 80+ km:    "4:1"  (elite ultra)

    Returns "3:1" for None / unknown distance (safe default).
    """
    if target_distance_km is None:
        return "3:1"
    if target_distance_km <= 15:
        return "1:1"
    if target_distance_km <= 30:
        return "2:1"
    if target_distance_km <= 80:
        return "3:1"
    return "4:1"


def _monday_of(d: datetime.date) -> datetime.date:
    """Return the Monday of the week containing `d`."""
    return d - datetime.timedelta(days=d.weekday())


def _parse_pattern(cycle_pattern: str) -> tuple[int, int]:
    """
    Parse a cycle_pattern string like "3:1" into (load_weeks, recovery_weeks).
    Defaults to (3, 1) on invalid input.
    """
    try:
        parts = cycle_pattern.split(":")
        if len(parts) != 2:
            raise ValueError
        load = int(parts[0])
        recovery = int(parts[1])
        if load < 1 or recovery < 1:
            raise ValueError
        return load, recovery
    except (ValueError, AttributeError):
        return 3, 1


# ── Main service ───────────────────────────────────────────────────────────────

def auto_periodize_athlete(
    athlete: Athlete,
    organization,
    cycle_pattern: str = "3:1",
    weeks_back: int = 12,
) -> dict:
    """
    Generate TrainingWeek records backward from the athlete's active goals.

    Algorithm per goal (sorted by effective_date ascending):
    1. Race week: phase="carrera" for the week containing the goal's date.
    2. Taper week: phase="descarga" for the week immediately before.
    3. Post-race week: phase="descanso" for the week immediately after.
    4. Fill backward from (race_week - 2) up to `weeks_back` weeks or the
       previous goal's post-race week (whichever is later) with the
       cycle_pattern (load_weeks load + recovery_week).

    Invariants:
    - NEVER overwrites an existing phase="lesion" (injury takes priority).
    - update_or_create — idempotent for all other phases.
    - Returns {"weeks_created": int, "weeks_updated": int, "phases": [...]}
    """
    if cycle_pattern not in VALID_PATTERNS:
        cycle_pattern = "3:1"

    load_weeks, recovery_weeks = _parse_pattern(cycle_pattern)

    today = datetime.date.today()
    today_monday = _monday_of(today)
    cutoff = today_monday - datetime.timedelta(weeks=weeks_back)

    # Fetch active/planned goals sorted by effective date
    goals_qs = (
        AthleteGoal.objects
        .filter(
            organization=organization,
            athlete=athlete,
            status__in=[AthleteGoal.Status.ACTIVE, AthleteGoal.Status.PLANNED],
        )
        .select_related("target_event")
        .order_by()  # we sort in Python below
    )

    def _effective_date(g: AthleteGoal) -> datetime.date | None:
        if g.target_date:
            return g.target_date
        if g.target_event_id and g.target_event:
            return g.target_event.event_date
        return None

    goals = sorted(
        [(g, _effective_date(g)) for g in goals_qs if _effective_date(g) is not None],
        key=lambda x: x[1],
    )

    if not goals:
        return {"weeks_created": 0, "weeks_updated": 0, "phases": [], "skipped_no_goals": True}

    # Pre-fetch all existing injury weeks for this athlete so we never overwrite them
    injury_weeks = set(
        TrainingWeek.objects
        .filter(organization=organization, athlete=athlete, phase=TrainingWeek.Phase.LESION)
        .values_list("week_start", flat=True)
    )

    weeks_created = 0
    weeks_updated = 0
    phases_out = []

    def _upsert(week_start: datetime.date, phase: str, goal_title: str | None = None):
        nonlocal weeks_created, weeks_updated
        if week_start in injury_weeks:
            return  # lesion — never overwrite
        tw, created = TrainingWeek.objects.update_or_create(
            organization=organization,
            athlete=athlete,
            week_start=week_start,
            defaults={"phase": phase},
        )
        if created:
            weeks_created += 1
        else:
            weeks_updated += 1
        entry = {"week_start": week_start.isoformat(), "phase": phase}
        if goal_title:
            entry["goal"] = goal_title
        phases_out.append(entry)

    # Track the end of coverage from previous goal (to avoid overwriting)
    previous_post_race_monday: datetime.date | None = None

    for goal, race_date in goals:
        race_monday = _monday_of(race_date)
        taper_monday = race_monday - datetime.timedelta(weeks=1)
        post_race_monday = race_monday + datetime.timedelta(weeks=1)

        # 1. Race week
        _upsert(race_monday, TrainingWeek.Phase.CARRERA, goal.title)
        # 2. Taper week (descarga)
        _upsert(taper_monday, TrainingWeek.Phase.DESCARGA)
        # 3. Post-race week (descanso)
        _upsert(post_race_monday, TrainingWeek.Phase.DESCANSO)

        # 4. Fill backward from taper - 1 up to cutoff or previous post-race
        fill_start = previous_post_race_monday or cutoff
        fill_end = taper_monday - datetime.timedelta(weeks=1)  # week before taper

        # Walk backward in cycle from fill_end to fill_start
        # We need to fill [fill_start, fill_end] with the cycle pattern.
        # The cycle "anchors" to the race: position 0 relative to taper
        # counts backward so the week immediately before taper is the end of a load block.

        total_weeks = []
        w = fill_end
        while w >= fill_start:
            total_weeks.append(w)
            w -= datetime.timedelta(weeks=1)

        # total_weeks is now [fill_end, fill_end-1w, ..., fill_start] — i.e., newest first
        # Assign cycle working from fill_end backward
        cycle_len = load_weeks + recovery_weeks
        # Position 0 = fill_end (immediately before taper) = last load week of a cycle block
        # The cycle repeats: load_weeks * carga, then recovery_weeks * descarga
        for i, week in enumerate(total_weeks):
            pos = i % cycle_len
            if pos < load_weeks:
                _upsert(week, TrainingWeek.Phase.CARGA)
            else:
                _upsert(week, TrainingWeek.Phase.DESCARGA)

        previous_post_race_monday = post_race_monday + datetime.timedelta(weeks=0)

    phases_out.sort(key=lambda x: x["week_start"])

    logger.info(
        "auto_periodize.completed",
        extra={
            "event_name": "auto_periodize.completed",
            "organization_id": organization.pk,
            "athlete_id": athlete.pk,
            "cycle_pattern": cycle_pattern,
            "weeks_created": weeks_created,
            "weeks_updated": weeks_updated,
            "goals_count": len(goals),
        },
    )

    return {
        "weeks_created": weeks_created,
        "weeks_updated": weeks_updated,
        "phases": phases_out,
    }
