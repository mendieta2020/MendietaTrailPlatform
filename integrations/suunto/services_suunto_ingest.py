"""
Suunto FIT ingestion service — provider-isolated (Law 4).

Maps parsed FIT data to CompletedActivity and persists idempotently.

LAW 3 INVARIANT: This module MUST NEVER import PlannedWorkout,
WorkoutAssignment, WorkoutBlock, or WorkoutInterval. Plan ≠ Real.

LAW 5 IDEMPOTENCY: Calling ingest_suunto_workout() twice with the same
(alumno_id, external_workout_id) produces exactly ONE CompletedActivity row.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ingest_suunto_workout(
    *,
    alumno_id: int,
    external_workout_id: str,
    fit_data: dict,
) -> tuple[object, bool]:
    """
    Persist a single Suunto workout as a CompletedActivity (idempotent).

    Args:
        alumno_id: pk of the Alumno who performed the workout.
        external_workout_id: Suunto workoutKey — used as provider_activity_id.
        fit_data: Normalized dict from integrations.suunto.parser.parse_fit_bytes().

    Returns:
        (CompletedActivity instance, created: bool)

    Raises:
        Alumno.DoesNotExist: if alumno_id is not found.
        ValueError: if fit_data is missing start_date or duration_s.
    """
    from core.models import Alumno, CompletedActivity  # lazy — Law 4 boundary

    alumno = Alumno.objects.select_related("entrenador").get(pk=alumno_id)
    organization = alumno.entrenador

    if organization is None:
        raise ValueError(
            f"ingest_suunto_workout: alumno {alumno_id} has no entrenador — "
            "cannot determine organization. Ingestion aborted."
        )

    start_date = fit_data.get("start_date")
    duration_s = fit_data.get("duration_s")

    if start_date is None:
        raise ValueError(
            f"ingest_suunto_workout: workout '{external_workout_id}' "
            "is missing 'start_date'. Cannot create CompletedActivity."
        )
    if duration_s is None:
        raise ValueError(
            f"ingest_suunto_workout: workout '{external_workout_id}' "
            "is missing 'duration_s'."
        )

    activity, created = CompletedActivity.objects.get_or_create(
        organization=organization,
        provider=CompletedActivity.Provider.SUUNTO,
        provider_activity_id=str(external_workout_id),
        defaults={
            "alumno": alumno,
            "sport": fit_data.get("sport") or "OTHER",
            "start_time": start_date,
            "duration_s": int(duration_s),
            "distance_m": float(fit_data.get("distance_m") or 0.0),
            "elevation_gain_m": fit_data.get("elevation_gain_m"),
            "raw_payload": {
                "provider": "suunto",
                "fit_summary": fit_data.get("raw_summary") or {},
                "calories_kcal": fit_data.get("calories_kcal"),
                "avg_hr": fit_data.get("avg_hr"),
            },
        },
    )

    logger.info(
        "suunto.ingest.created" if created else "suunto.ingest.duplicate_noop",
        extra={
            "event_name": "suunto.ingest.created" if created else "suunto.ingest.duplicate_noop",
            "organization_id": organization.pk,
            "alumno_id": alumno_id,
            "provider_activity_id": external_workout_id,
            "outcome": "success" if created else "noop",
        },
    )
    return activity, created
