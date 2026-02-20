# PR7: canonical location → integrations/strava/mapper.py
# This shim re-exports everything so existing import paths remain valid.
from integrations.strava.mapper import (  # noqa: F401
    compute_source_hash,
    map_strava_activity_to_actividad,
    normalize_strava_activity,
    supported_strava_activity_type,
)
