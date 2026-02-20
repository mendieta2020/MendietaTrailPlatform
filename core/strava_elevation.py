# PR7: canonical location → integrations/strava/elevation.py
# This shim re-exports everything so existing import paths remain valid.
from integrations.strava.elevation import (  # noqa: F401
    compute_elevation_loss_m,
    smooth_altitude,
)
