"""
integrations/suunto/guides.py

Pure payload builder for SuuntoPlus Guides (outbound workout push).

PLAN ≠ REAL INVARIANT:
    This module ONLY reads planning-side models:
        PlannedWorkout, WorkoutBlock, WorkoutInterval.
    It NEVER imports or queries CompletedActivity, ActivityStream,
    or any execution-side model.

Provider boundary (Law 4):
    All Suunto-specific JSON shaping lives here exclusively.
    Domain models (core/) never call this directly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import PlannedWorkout


def build_guide_payload(planned_workout: "PlannedWorkout") -> dict:
    """
    Translate a PlannedWorkout (with its blocks and intervals) into the
    JSON payload expected by the SuuntoPlus Guides API.

    Args:
        planned_workout: A PlannedWorkout instance. Blocks and intervals
            must be prefetched by the caller for efficiency.

    Returns:
        dict: Suunto Guide JSON payload ready to POST to /guide.

    Guarantees:
        - Never touches CompletedActivity or any execution-side model.
        - Pure function: no DB writes, no HTTP calls.
    """
    blocks = []
    for block in planned_workout.blocks.prefetch_related("intervals").order_by("order_index"):
        steps = []
        for interval in block.intervals.order_by("order_index"):
            step: dict = {
                "order": interval.order_index,
                "metricType": interval.metric_type,
                "description": interval.description,
            }
            if interval.duration_seconds is not None:
                step["durationSeconds"] = interval.duration_seconds
            if interval.distance_meters is not None:
                step["distanceMeters"] = interval.distance_meters
            if interval.target_value_low is not None:
                step["targetLow"] = interval.target_value_low
            if interval.target_value_high is not None:
                step["targetHigh"] = interval.target_value_high
            if interval.target_label:
                step["targetLabel"] = interval.target_label
            if interval.recovery_seconds is not None:
                step["recoverySeconds"] = interval.recovery_seconds
            if interval.recovery_distance_meters is not None:
                step["recoveryDistanceMeters"] = interval.recovery_distance_meters
            steps.append(step)

        block_entry: dict = {
            "order": block.order_index,
            "blockType": block.block_type,
            "name": block.name or block.block_type,
            "steps": steps,
        }
        if block.description:
            block_entry["description"] = block.description
        blocks.append(block_entry)

    payload: dict = {
        "guideName": planned_workout.name,
        "sport": planned_workout.discipline,
        "structureVersion": planned_workout.structure_version,
        "blocks": blocks,
    }
    if planned_workout.description:
        payload["description"] = planned_workout.description
    if planned_workout.estimated_duration_seconds is not None:
        payload["estimatedDurationSeconds"] = planned_workout.estimated_duration_seconds
    if planned_workout.estimated_distance_meters is not None:
        payload["estimatedDistanceMeters"] = planned_workout.estimated_distance_meters

    return payload
