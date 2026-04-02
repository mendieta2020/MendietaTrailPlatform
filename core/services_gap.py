"""
core/services_gap.py

Grade Adjusted Pace (GAP) computation service for trail/running activities.

Uses a simplified Minetti cost-of-transport model:
  cost_factor = 1 + (avg_grade * 10)
  gap = actual_pace / cost_factor

This approximates the metabolic cost of gradient running, where each 1% of
average grade adds roughly 10% to the energy expenditure at the same pace.

Laws:
- No PII stored or logged (Law 6).
- Provider-agnostic: works with normalized CompletedActivity fields only (Law 4).
"""
from __future__ import annotations


def compute_gap(
    distance_m: float,
    elevation_gain_m: float,
    duration_s: float,
) -> float | None:
    """
    Compute Grade Adjusted Pace (seconds/km) using a simplified Minetti model.

    Returns the equivalent flat-ground pace for a hilly effort.

    Formula:
        avg_grade    = elevation_gain_m / distance_m
        cost_factor  = 1 + (avg_grade * 10)  # each 1% grade ≈ +10% cost
        actual_pace  = duration_s / (distance_m / 1000)  # s/km
        gap          = actual_pace / cost_factor

    Returns None if distance_m ≤ 0, duration_s ≤ 0, or inputs are missing.
    """
    if not distance_m or not duration_s or distance_m <= 0 or duration_s <= 0:
        return None

    elev = elevation_gain_m or 0.0
    avg_grade = elev / distance_m
    cost_factor = 1.0 + (avg_grade * 10.0)
    cost_factor = max(0.1, cost_factor)  # guard against pathological negatives

    actual_pace_s_km = duration_s / (distance_m / 1000.0)
    gap = actual_pace_s_km / cost_factor
    return round(gap, 2)


def format_pace(seconds_per_km: float) -> str:
    """
    Convert seconds/km to 'M:SS' display string.

    Example: 345.0 → '5:45'
    """
    s = int(round(seconds_per_km))
    return f"{s // 60}:{s % 60:02d}"
