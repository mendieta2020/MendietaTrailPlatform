"""
Strava activity ingestion service — provider-isolated (Law 4).

Maps normalized Strava activity data to CompletedActivity and persists
idempotently.

LAW 3 INVARIANT: This module MUST NEVER import PlannedWorkout,
WorkoutAssignment, WorkoutBlock, or WorkoutInterval. Plan ≠ Real.

LAW 5 IDEMPOTENCY: Calling ingest_strava_activity() twice with the same
(alumno_id, external_activity_id) produces exactly ONE CompletedActivity row.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Mapping from Strava activity type strings to TIPO_ACTIVIDAD choices.
_STRAVA_SPORT_MAP: dict[str, str] = {
    "RUN": "RUN",
    "TRAILRUN": "TRAIL",
    "VIRTUALRUN": "RUN",
    "RIDE": "CYCLING",
    "VIRTUALRIDE": "INDOOR_BIKE",
    "EBIKERIDE": "CYCLING",
    "MOUNTAINBIKERIDE": "MTB",
    "GRAVELRIDE": "CYCLING",
    "ROADBIKERIDE": "CYCLING",
    "WALK": "OTHER",
    "HIKE": "TRAIL",
    "WORKOUT": "CARDIO",
    "SWIM": "SWIMMING",
    "WEIGHTTRAINING": "STRENGTH",
}


def _normalize_sport(strava_type: str | None) -> str:
    """Map Strava activity type to a TIPO_ACTIVIDAD value. Falls back to OTHER."""
    key = (strava_type or "").upper().replace(" ", "")
    return _STRAVA_SPORT_MAP.get(key, "OTHER")


def ingest_strava_activity(
    *,
    alumno_id: int,
    external_activity_id: str,
    activity_data: dict,
) -> tuple[object, bool]:
    """
    Persist a single Strava activity as a CompletedActivity (idempotent).

    Args:
        alumno_id: pk of the Alumno who performed the activity.
        external_activity_id: Strava activity ID — used as provider_activity_id.
        activity_data: Normalized dict. Expected keys:
            start_date_local (datetime), elapsed_time_s (int), distance_m (float),
            type (str, Strava activity type), elevation_m (float | None),
            calories_kcal (float | None), avg_hr (float | None), raw (dict).

    Returns:
        (CompletedActivity instance, created: bool)

    Raises:
        Alumno.DoesNotExist: if alumno_id is not found.
        ValueError: if activity_data is missing start_date_local or elapsed_time_s.
    """
    from core.models import Alumno, Athlete, CompletedActivity, Membership  # lazy — Law 4 boundary

    alumno = Alumno.objects.select_related("entrenador").get(pk=alumno_id)

    if alumno.entrenador is None:
        raise ValueError(
            f"ingest_strava_activity: alumno {alumno_id} has no entrenador — "
            "cannot determine organization. Ingestion aborted."
        )

    membership = (
        Membership.objects
        .filter(user=alumno.entrenador, role__in=["owner", "coach"], is_active=True)
        .select_related("organization")
        .first()
    )
    if membership is None:
        raise ValueError(
            f"ingest_strava_activity: entrenador (user_id={alumno.entrenador_id}) "
            "has no active coach/owner Membership — cannot determine organization. "
            "Ingestion aborted."
        )
    organization = membership.organization

    # Bridge to organization-first Athlete — None if alumno has no linked user
    # or no Athlete row exists for this org. Never blocks ingestion (Law 5).
    athlete = None
    if alumno.usuario_id is not None:
        athlete = Athlete.objects.filter(
            organization=organization, user_id=alumno.usuario_id
        ).first()

    start_date = activity_data.get("start_date_local")
    elapsed_time_s = activity_data.get("elapsed_time_s")

    if start_date is None:
        raise ValueError(
            f"ingest_strava_activity: activity '{external_activity_id}' "
            "is missing 'start_date_local'. Cannot create CompletedActivity."
        )
    if elapsed_time_s is None:
        raise ValueError(
            f"ingest_strava_activity: activity '{external_activity_id}' "
            "is missing 'elapsed_time_s'."
        )

    activity, created = CompletedActivity.objects.get_or_create(
        organization=organization,
        provider=CompletedActivity.Provider.STRAVA,
        provider_activity_id=str(external_activity_id),
        defaults={
            "alumno": alumno,
            "athlete": athlete,
            "sport": _normalize_sport(activity_data.get("type")),
            "start_time": start_date,
            "duration_s": int(elapsed_time_s),
            "distance_m": float(activity_data.get("distance_m") or 0.0),
            "elevation_gain_m": activity_data.get("elevation_m"),
            "raw_payload": {
                "provider": "strava",
                "strava_activity_id": str(external_activity_id),
                "calories_kcal": activity_data.get("calories_kcal"),
                "avg_hr": activity_data.get("avg_hr"),
                "raw": activity_data.get("raw") or {},
            },
        },
    )

    logger.info(
        "strava.ingest.created" if created else "strava.ingest.duplicate_noop",
        extra={
            "event_name": "strava.ingest.created" if created else "strava.ingest.duplicate_noop",
            "organization_id": organization.pk,
            "alumno_id": alumno_id,
            "athlete_id": athlete.pk if athlete else None,
            "provider_activity_id": external_activity_id,
            "outcome": "success" if created else "noop",
        },
    )
    return activity, created
