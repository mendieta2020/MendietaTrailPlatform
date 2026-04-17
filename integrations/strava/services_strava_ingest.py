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


def backfill_strava_activities(
    *,
    alumno_id: int,
    access_token: str,
    years: int = 5,
    days: int | None = None,
) -> dict:
    """
    Fetch paginated Strava /athlete/activities and persist each as CompletedActivity.

    Idempotent: calls ingest_strava_activity() which uses get_or_create —
    safe to rerun; already-persisted activities are counted as 'skipped'.

    Raises requests.HTTPError on non-2xx Strava responses so the Celery task
    can apply its retry policy.

    Args:
        alumno_id:    PK of the Alumno — passed directly to ingest_strava_activity.
        access_token: Valid Strava OAuth access token (NEVER logged).
        years:        How many years back to import (clamped to 1–10).
                      Ignored when `days` is provided.
        days:         If set, use exactly this many days back instead of `years`.
                      Useful for onboarding backfill (e.g. days=90). Not clamped.

    Returns:
        {"created": int, "skipped": int, "errors": int}
    """
    import datetime

    import requests
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    if days is not None:
        after_dt = timezone.now() - datetime.timedelta(days=days)
    else:
        years = max(1, min(years, 10))
        after_dt = timezone.now() - datetime.timedelta(days=365 * years)
    after_ts = int(after_dt.timestamp())

    created = 0
    skipped = 0
    errors = 0
    page = 1

    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after_ts, "per_page": 200, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        activities = resp.json()

        if not activities:
            break

        for act in activities:
            try:
                raw_start = act.get("start_date_local") or act.get("start_date")
                start_dt = None
                if raw_start:
                    # Normalize Z suffix for Python <3.11 compatibility
                    normalized = (
                        raw_start[:-1] + "+00:00"
                        if raw_start.endswith("Z")
                        else raw_start
                    )
                    start_dt = parse_datetime(normalized)
                    if start_dt and timezone.is_naive(start_dt):
                        start_dt = timezone.make_aware(start_dt)

                activity_data = {
                    "start_date_local": start_dt,
                    "elapsed_time_s": act.get("elapsed_time"),
                    "distance_m": float(act.get("distance") or 0),
                    "type": act.get("sport_type") or act.get("type"),
                    "elevation_m": act.get("total_elevation_gain"),
                    "calories_kcal": act.get("calories"),
                    "avg_hr": act.get("average_heartrate"),
                    "raw": act,
                }

                _, was_created = ingest_strava_activity(
                    alumno_id=alumno_id,
                    external_activity_id=str(act["id"]),
                    activity_data=activity_data,
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

            except Exception as exc:
                logger.warning(
                    "strava.backfill.activity_error",
                    extra={
                        "event_name": "strava.backfill.activity_error",
                        "alumno_id": alumno_id,
                        "strava_activity_id": act.get("id"),
                        "exc": str(exc),
                    },
                )
                errors += 1

        page += 1

    return {"created": created, "skipped": skipped, "errors": errors}


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

    # --- Extract normalized biometric fields from provider payload ---
    # These go into dedicated columns so the PMC engine (services_pmc.py)
    # never needs to read raw_payload (Law 4 — provider boundary isolation).
    raw = activity_data.get("raw") or {}
    _avg_hr_raw = activity_data.get("avg_hr") or raw.get("average_heartrate")
    _max_hr_raw = raw.get("max_heartrate")
    _avg_watts_raw = raw.get("average_watts")
    _avg_speed_ms = raw.get("average_speed")  # m/s from Strava
    _avg_pace_s_km: float | None = (
        (1000.0 / _avg_speed_ms) if _avg_speed_ms and _avg_speed_ms > 0 else None
    )

    # Use update_or_create so webhook update events refresh existing CompletedActivity rows.
    # The lookup key is (organization, provider, provider_activity_id) — guaranteed unique.
    # PMC dispatch (below) fires only on creation to avoid duplicate queue noise.
    _ca_defaults = {
        "alumno": alumno,
        "athlete": athlete,
        "sport": _normalize_sport(activity_data.get("type")),
        "start_time": start_date,
        "duration_s": int(elapsed_time_s),
        "distance_m": float(activity_data.get("distance_m") or 0.0),
        "elevation_gain_m": activity_data.get("elevation_m"),
        # Normalized biometric fields (provider-agnostic)
        "avg_hr": int(_avg_hr_raw) if _avg_hr_raw is not None else None,
        "max_hr": int(_max_hr_raw) if _max_hr_raw is not None else None,
        "avg_power_w": int(_avg_watts_raw) if _avg_watts_raw is not None else None,
        "avg_pace_s_km": _avg_pace_s_km,
        "raw_payload": {
            "provider": "strava",
            "strava_activity_id": str(external_activity_id),
            "calories_kcal": activity_data.get("calories_kcal"),
            "avg_hr": activity_data.get("avg_hr"),
            "raw": raw,
        },
    }
    activity, created = CompletedActivity.objects.update_or_create(
        organization=organization,
        provider=CompletedActivity.Provider.STRAVA,
        provider_activity_id=str(external_activity_id),
        defaults=_ca_defaults,
    )

    # Dispatch PMC computation task after a new activity is persisted.
    # Idempotent: the task itself is safe to rerun (uses update_or_create).
    # Do NOT dispatch for duplicates — noop would just add queue noise.
    if created:
        try:
            from core.tasks import compute_pmc_for_activity
            compute_pmc_for_activity.delay(activity.pk)
        except Exception:
            # PMC computation is non-blocking — never fail ingestion for it.
            logger.warning(
                "strava.ingest.pmc_dispatch_failed",
                extra={
                    "event_name": "strava.ingest.pmc_dispatch_failed",
                    "organization_id": organization.pk,
                    "provider_activity_id": str(external_activity_id),
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
