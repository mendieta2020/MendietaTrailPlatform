"""
core/services_pmc.py

Provider-agnostic PMC (Performance Management Chart) engine for Quantoryn.

Model FK clarification:
- CompletedActivity.athlete → Athlete (org-first FK, may be None for legacy rows)
- AthleteHRProfile.athlete → AUTH_USER_MODEL (User)
- ActivityLoad.athlete      → AUTH_USER_MODEL (User)
- DailyLoad.athlete         → AUTH_USER_MODEL (User)

All PMC computation flows through User FK so the engine is Athlete-model-independent.

Laws enforced:
- Law 1 (multi-tenant): every query scopes to organization.
- Law 3 (Plan ≠ Real): reads CompletedActivity only — never PlannedWorkout.
- Law 4 (provider boundary): reads normalized biometric fields (avg_hr,
  avg_pace_s_km, tss_override) — never raw_payload.
- Law 5 (idempotency): process_activity_load is safe to rerun.
- Law 6 (secrets): no PII logged (PKs only, no names/emails).
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# Banister model decay constants
_CTL_DECAY = math.exp(-1.0 / 42)   # 42-day fitness window
_ATL_DECAY = math.exp(-1.0 / 7)    # 7-day fatigue window
_CTL_FACTOR = 1.0 - _CTL_DECAY
_ATL_FACTOR = 1.0 - _ATL_DECAY

# Banister TRIMP gender-neutral exponent coefficient
_TRIMP_K = 1.92


# ── Sport intensity factors (duration-based fallback) ──────────────────────

_SPORT_INTENSITY: dict[str, float] = {
    "trail": 0.70,
    "trail_run": 0.70,
    "run": 0.65,
    "cycling": 0.60,
    "ride": 0.60,
    "indoor_bike": 0.55,
    "mtb": 0.65,
    "swimming": 0.55,
    "swim": 0.55,
    "cardio": 0.50,
    "strength": 0.45,
    "hike": 0.45,
    "other": 0.45,
    "walk": 0.35,
}


def _sport_intensity_factor(sport: str) -> float:
    """Default intensity factor by sport for duration-based TSS estimate."""
    return _SPORT_INTENSITY.get((sport or "").lower(), 0.55)


# ── TSB zone helpers ────────────────────────────────────────────────────────

def tsb_zone(tsb: float) -> str:
    """Return TSB zone label for UI display."""
    if tsb >= 25:
        return "fresh"
    elif tsb >= 0:
        return "optimal"
    elif tsb >= -10:
        return "productive"
    elif tsb >= -30:
        return "fatigued"
    else:
        return "overreaching"


def compute_ars(tsb: float) -> int:
    """Athlete Readiness Score 0–100 derived from TSB zone."""
    if tsb >= 25:
        return 90
    elif tsb >= 0:
        return 72
    elif tsb >= -10:
        return 55
    elif tsb >= -30:
        return 35
    else:
        return 15


# ── TSS cascade ─────────────────────────────────────────────────────────────

def compute_tss_for_activity(activity, hr_profile) -> tuple[float, str]:
    """
    Compute TSS for a CompletedActivity using a 4-level priority cascade.

    Priority:
    1. tss_override  — provider-supplied TSS (Polar, Garmin Training Load).
    2. TRIMP         — Banister 1991 from avg_hr + hr_profile.
    3. rTSS          — running TSS from avg_pace + threshold_pace (no HR).
    4. Duration      — last resort: (duration_hours * sport_factor * 100).

    Args:
        activity:   CompletedActivity instance with normalized biometric fields.
        hr_profile: AthleteHRProfile instance with hr_max, hr_rest, threshold_pace_s_km.

    Returns:
        (tss, method) where method is one of:
        override / trimp / rtss_pace / estimated_duration
    """
    # Priority 1: provider-supplied TSS override
    if activity.tss_override is not None:
        return round(float(activity.tss_override), 2), "override"

    # Priority 2: Banister TRIMP from heart rate
    if activity.avg_hr is not None:
        hr_rest = hr_profile.hr_rest
        hr_max = hr_profile.hr_max
        hr_reserve = hr_max - hr_rest
        if hr_reserve > 0:
            duration_min = activity.duration_s / 60.0
            hr_ratio = (activity.avg_hr - hr_rest) / hr_reserve
            hr_ratio = max(0.0, min(1.0, hr_ratio))  # clamp to [0, 1]
            # Banister TRIMP (1991): T * HRr * 0.64 * e^(k * HRr)
            trimp = duration_min * hr_ratio * 0.64 * math.exp(_TRIMP_K * hr_ratio)
            return round(trimp, 2), "trimp"

    # Priority 3: rTSS from pace (running without HR)
    if (
        activity.avg_pace_s_km is not None
        and hr_profile.threshold_pace_s_km is not None
        and activity.avg_pace_s_km > 0
        and hr_profile.threshold_pace_s_km > 0
    ):
        duration_hours = activity.duration_s / 3600.0
        # Intensity Factor = threshold_pace / avg_pace (faster = higher IF)
        intensity_factor = hr_profile.threshold_pace_s_km / activity.avg_pace_s_km
        intensity_factor = max(0.5, min(1.5, intensity_factor))
        rtss = (intensity_factor ** 2) * duration_hours * 100.0
        return round(rtss, 2), "rtss_pace"

    # Priority 4: duration-based estimate by sport (last resort)
    duration_hours = activity.duration_s / 3600.0
    sport_factor = _sport_intensity_factor(activity.sport)
    estimated = duration_hours * sport_factor * 100.0
    return round(estimated, 2), "estimated_duration"


# ── PMC computation (CTL / ATL / TSB) ──────────────────────────────────────

def compute_pmc_from_date(user, organization, from_date: date) -> None:
    """
    Recompute CTL/ATL/TSB for all days from from_date to today (inclusive).

    Reads ActivityLoad sums per day; bulk-upserts DailyLoad rows.
    Only recomputes forward from the given start date — efficient for incremental updates.

    Args:
        user:          AUTH_USER_MODEL instance (User, not Athlete).
        organization:  Organization instance.
        from_date:     First date to recompute (typically activity.start_time.date()).
    """
    from core.models import ActivityLoad, DailyLoad

    # Seed: load CTL/ATL from the day immediately before from_date
    seed_date = from_date - timedelta(days=1)
    seed = DailyLoad.objects.filter(
        organization=organization,
        athlete=user,
        date=seed_date,
    ).first()
    ctl = seed.ctl if seed else 0.0
    atl = seed.atl if seed else 0.0

    # Pre-fetch ActivityLoad daily sums from from_date to today
    today = timezone.now().date()
    tss_qs = (
        ActivityLoad.objects.filter(
            organization=organization,
            athlete=user,
            date__gte=from_date,
            date__lte=today,
        )
        .values("date")
        .annotate(total_tss=Sum("tss"))
        .order_by("date")
    )
    tss_by_date: dict[date, float] = {
        row["date"]: float(row["total_tss"]) for row in tss_qs
    }

    # Walk day-by-day, computing EWA
    daily_loads = []
    current = from_date
    while current <= today:
        day_tss = tss_by_date.get(current, 0.0)
        ctl = ctl * _CTL_DECAY + day_tss * _CTL_FACTOR
        atl = atl * _ATL_DECAY + day_tss * _ATL_FACTOR
        tsb = ctl - atl
        ars = compute_ars(tsb)
        daily_loads.append(
            DailyLoad(
                organization=organization,
                athlete=user,
                date=current,
                tss=round(day_tss, 2),
                ctl=round(ctl, 2),
                atl=round(atl, 2),
                tsb=round(tsb, 2),
                ars=ars,
            )
        )
        current += timedelta(days=1)

    # Bulk upsert — idempotent
    DailyLoad.objects.bulk_create(
        daily_loads,
        update_conflicts=True,
        unique_fields=["organization", "athlete", "date"],
        update_fields=["tss", "ctl", "atl", "tsb", "ars", "computed_at"],
    )


# ── Full athlete recompute (triggered when HR profile changes) ─────────────

def compute_pmc_for_athlete_full(user_id: int, organization_id: int) -> None:
    """
    Recompute the full PMC history for an athlete (from earliest ActivityLoad to today).

    Triggered when an athlete updates their HR profile. Safe to rerun.

    Args:
        user_id:         AUTH_USER_MODEL PK.
        organization_id: Organization PK.
    """
    from django.contrib.auth import get_user_model

    from core.models import ActivityLoad, AthleteHRProfile, CompletedActivity, Organization

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        organization = Organization.objects.get(pk=organization_id)
    except (User.DoesNotExist, Organization.DoesNotExist):
        logger.warning(
            "pmc_full_recompute_skipped_missing",
            extra={
                "event_name": "pmc_full_recompute_skipped_missing",
                "user_id": user_id,
                "organization_id": organization_id,
            },
        )
        return

    hr_profile, _ = AthleteHRProfile.objects.get_or_create(
        organization=organization,
        athlete=user,
        defaults={"hr_max": 190, "hr_rest": 55},
    )

    # Recompute ActivityLoad for all activities linked to this user via Athlete.user
    activities = CompletedActivity.objects.filter(
        organization=organization,
        athlete__user=user,
    ).order_by("start_time")

    for activity in activities:
        tss, method = compute_tss_for_activity(activity, hr_profile)
        ActivityLoad.objects.update_or_create(
            completed_activity=activity,
            defaults={
                "organization": organization,
                "athlete": user,
                "date": activity.start_time.date(),
                "tss": tss,
                "method": method,
            },
        )
        CompletedActivity.objects.filter(pk=activity.pk).update(
            canonical_load=tss,
            canonical_method=method,
        )

    # Recompute PMC from the earliest ActivityLoad date
    earliest = (
        ActivityLoad.objects.filter(organization=organization, athlete=user)
        .order_by("date")
        .values_list("date", flat=True)
        .first()
    )
    if earliest:
        compute_pmc_from_date(user=user, organization=organization, from_date=earliest)

    logger.info(
        "pmc_full_recompute_done",
        extra={
            "event_name": "pmc_full_recompute_done",
            "organization_id": organization_id,
            "user_id": user_id,
            "outcome": "success",
        },
    )


# ── Entry point (called from Celery task) ──────────────────────────────────

def process_activity_load(completed_activity_id: int) -> None:
    """
    Full PMC pipeline for a single CompletedActivity:

    1. Load CompletedActivity + AthleteHRProfile (get_or_create with defaults).
    2. Compute TSS via 4-level cascade → save ActivityLoad (idempotent).
    3. Update CompletedActivity.canonical_load + canonical_method.
    4. Recompute DailyLoad forward from this activity's date.

    Idempotent: safe to rerun for the same activity.
    Skips silently if activity.athlete is None (backward compat rows without Athlete FK).
    """
    from core.models import ActivityLoad, AthleteHRProfile, CompletedActivity

    try:
        activity = CompletedActivity.objects.select_related(
            "organization", "athlete__user"
        ).get(pk=completed_activity_id)
    except CompletedActivity.DoesNotExist:
        logger.warning(
            "pmc_activity_not_found",
            extra={
                "event_name": "pmc_activity_not_found",
                "completed_activity_id": completed_activity_id,
            },
        )
        return

    # activity.athlete is FK to Athlete model (not User directly)
    # Rows ingested before PR-114 may have athlete=None — skip silently (Law 5)
    if activity.athlete is None:
        logger.warning(
            "pmc_skipped_no_athlete",
            extra={
                "event_name": "pmc_skipped_no_athlete",
                "completed_activity_id": completed_activity_id,
                "organization_id": activity.organization_id,
            },
        )
        return

    org = activity.organization
    user = activity.athlete.user  # AUTH_USER_MODEL instance

    hr_profile, _ = AthleteHRProfile.objects.get_or_create(
        organization=org,
        athlete=user,
        defaults={"hr_max": 190, "hr_rest": 55},
    )

    tss, method = compute_tss_for_activity(activity, hr_profile)

    # Persist ActivityLoad (idempotent via OneToOne)
    ActivityLoad.objects.update_or_create(
        completed_activity=activity,
        defaults={
            "organization": org,
            "athlete": user,
            "date": activity.start_time.date(),
            "tss": tss,
            "method": method,
        },
    )

    # Update canonical fields on CompletedActivity
    CompletedActivity.objects.filter(pk=activity.pk).update(
        canonical_load=tss,
        canonical_method=method,
    )

    # Recompute PMC forward from this activity's date
    compute_pmc_from_date(
        user=user,
        organization=org,
        from_date=activity.start_time.date(),
    )

    logger.info(
        "pmc_computed",
        extra={
            "event_name": "pmc_computed",
            "organization_id": org.pk,
            "user_id": user.pk,
            "completed_activity_id": activity.pk,
            "tss": tss,
            "method": method,
            "outcome": "success",
        },
    )
