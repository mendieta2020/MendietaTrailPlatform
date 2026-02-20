# PR7: canonical location → integrations/strava/normalizer.py
# This shim re-exports everything so existing import paths remain valid.
from integrations.strava.normalizer import (  # noqa: F401
    NormalizedStravaBusinessActivity,
    ProductDecision,
    SportType,
    _coalesce,
    _ensure_tz_aware,
    _normalize_strava_sport_type,
    _to_float,
    _to_int,
    decide_activity_creation,
    extract_strava_sport_type,
    normalize_strava_activity_payload,
)
