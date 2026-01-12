from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone


# Plan (P1.4): centralize range parsing + limits so PMC/week-summary share the same behavior.

def max_range_days() -> int:
    return int(getattr(settings, "ANALYTICS_MAX_RANGE_DAYS", 365))


def range_days(start: date, end: date) -> int:
    return (end - start).days + 1


def parse_date_range_params(
    start_str: str | None,
    end_str: str | None,
    *,
    default_days: int = 365,
    enforce_max_for_custom: bool = True,
) -> tuple[date, date, bool]:
    """
    Parse explicit start/end params. If not provided, fall back to default window.
    Returns (start, end, is_custom_range).
    """
    if start_str or end_str:
        if not (start_str and end_str):
            raise ValueError("start_end_required")
        start = date.fromisoformat(str(start_str))
        end = date.fromisoformat(str(end_str))
        if start > end:
            raise ValueError("start_after_end")
        if enforce_max_for_custom and range_days(start, end) > max_range_days():
            raise ValueError("range_too_large")
        return start, end, True

    end = timezone.localdate()
    start = end - timedelta(days=default_days)
    return start, end, False


def parse_iso_week_param(week_str: str | None) -> tuple[date, date, str]:
    """
    week=YYYY-Www (ISO week). Returns (start_monday, end_sunday, canonical_week_str).
    """
    if not week_str:
        today = timezone.localdate()
        year, week, _ = today.isocalendar()
        week_str = f"{year}-{week:02d}"

    s = str(week_str).strip().upper().replace("W", "").replace("_", "-")
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError("invalid_week_format")
    year = int(parts[0])
    week = int(parts[1])
    start = date.fromisocalendar(year, week, 1)
    end = start + timedelta(days=6)
    return start, end, f"{year}-W{week:02d}"
