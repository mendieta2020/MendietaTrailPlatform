"""
core/services_analytics.py

P2 analytics services — organization-scoped.

Compute PMC (Performance Management Chart) metrics from WorkoutAssignment
planned TSS data. Planning-side only — Plan ≠ Real invariant is enforced:
CompletedActivity execution data is never read here.
"""
import logging
import math
from datetime import date, timedelta
from typing import Any

from django.db.models import FloatField, Sum
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)

# Banister model time constants (days)
_CTL_TAU = 42  # Chronic Training Load — fitness window
_ATL_TAU = 7   # Acute Training Load — fatigue window
_CTL_DECAY = math.exp(-1.0 / _CTL_TAU)
_ATL_DECAY = math.exp(-1.0 / _ATL_TAU)


def compute_org_pmc(
    *,
    organization,
    days: int = 90,
) -> dict[str, Any]:
    """
    Compute organization-level PMC (CTL/ATL/TSB) from WorkoutAssignment planned TSS.

    Data path: WorkoutAssignment → planned_workout → planned_tss
    Plan ≠ Real invariant: only the planning side is queried. CompletedActivity
    data is never accessed.

    Args:
        organization: Organization instance (already resolved by the view's tenancy gate).
        days: Number of trailing days to compute (default 90).

    Returns:
        {
            "active_athletes_count": int,
            "pmc_series": [
                {"date": "YYYY-MM-DD", "ctl": float, "atl": float, "tsb": float},
                ...  # one entry per day, oldest first
            ],
        }
    """
    # Import inside function to avoid circular imports
    from core.models import Athlete, WorkoutAssignment

    today = date.today()
    start_date = today - timedelta(days=days - 1)

    active_athletes_count = Athlete.objects.filter(organization=organization).count()

    # Aggregate planned TSS per calendar date within the window
    tss_qs = (
        WorkoutAssignment.objects.filter(
            organization=organization,
            scheduled_date__gte=start_date,
            scheduled_date__lte=today,
            planned_workout__planned_tss__isnull=False,
        )
        .values("scheduled_date")
        .annotate(
            daily_tss=Coalesce(
                Sum("planned_workout__planned_tss"),
                0.0,
                output_field=FloatField(),
            )
        )
        .order_by("scheduled_date")
    )

    tss_map: dict[date, float] = {
        row["scheduled_date"]: float(row["daily_tss"]) for row in tss_qs
    }

    # Walk day by day, computing CTL/ATL with Banister EWMA
    ctl = 0.0
    atl = 0.0
    series: list[dict] = []
    current = start_date
    while current <= today:
        tss = tss_map.get(current, 0.0)
        ctl = ctl * _CTL_DECAY + tss * (1.0 - _CTL_DECAY)
        atl = atl * _ATL_DECAY + tss * (1.0 - _ATL_DECAY)
        tsb = ctl - atl
        series.append(
            {
                "date": current.isoformat(),
                "ctl": round(ctl, 2),
                "atl": round(atl, 2),
                "tsb": round(tsb, 2),
            }
        )
        current += timedelta(days=1)

    logger.info(
        "dashboard_analytics.computed",
        extra={
            "event_name": "dashboard_analytics.computed",
            "organization_id": organization.pk,
            "days": days,
            "active_athletes": active_athletes_count,
            "series_length": len(series),
            "outcome": "success",
        },
    )

    return {
        "active_athletes_count": active_athletes_count,
        "pmc_series": series,
    }


def compute_athlete_pmc_real(
    *,
    organization,
    athlete,
    days: int = 90,
) -> list[dict]:
    """
    Compute real-side PMC (CTL/ATL/TSB) from CompletedActivity execution data.

    PLAN ≠ REAL: this function reads CompletedActivity only.
    Never reads PlannedWorkout or WorkoutAssignment.

    TSS estimate per activity: (duration_s / 3600) * 100  (simplified, no HR data)
    CTL/ATL computed with Banister EWMA model over the requested window.

    Args:
        organization: Organization instance (already validated by the view's tenancy gate).
        athlete: Athlete instance (must belong to organization — caller's responsibility).
        days: Trailing window in days (default 90).

    Returns:
        List of dicts ordered by date ASC:
        [{"date": "YYYY-MM-DD", "tss": float, "ctl": float, "atl": float, "tsb": float}, ...]
    """
    from django.db.models.functions import TruncDate

    from core.models import CompletedActivity

    today = date.today()
    start_date = today - timedelta(days=days - 1)

    rows = (
        CompletedActivity.objects.filter(
            organization=organization,
            athlete=athlete,
            start_time__date__gte=start_date,
            start_time__date__lte=today,
            deleted_at__isnull=True,
        )
        .annotate(activity_date=TruncDate("start_time"))
        .values_list("activity_date", "duration_s")
    )

    # Aggregate TSS per day in Python — one row per (date, activity)
    tss_map: dict[date, float] = {}
    activity_count = 0
    for activity_date, duration_s in rows:
        tss = (duration_s / 3600.0) * 100.0
        tss_map[activity_date] = tss_map.get(activity_date, 0.0) + tss
        activity_count += 1

    # Walk day by day, computing CTL/ATL with Banister EWMA
    ctl = 0.0
    atl = 0.0
    series: list[dict] = []
    current = start_date
    while current <= today:
        tss = tss_map.get(current, 0.0)
        tsb = round(ctl - atl, 2)  # TSB = CTL(day-1) - ATL(day-1), computed before today's load
        ctl = ctl * _CTL_DECAY + tss * (1.0 - _CTL_DECAY)
        atl = atl * _ATL_DECAY + tss * (1.0 - _ATL_DECAY)
        series.append(
            {
                "date": current.isoformat(),
                "tss": round(tss, 2),
                "ctl": round(ctl, 2),
                "atl": round(atl, 2),
                "tsb": tsb,
            }
        )
        current += timedelta(days=1)

    logger.info(
        "athlete_pmc_real.computed",
        extra={
            "event_name": "athlete_pmc_real.computed",
            "organization_id": organization.pk,
            "athlete_id": athlete.pk,
            "days": days,
            "activity_count": activity_count,
            "series_length": len(series),
            "outcome": "success",
        },
    )

    return series
