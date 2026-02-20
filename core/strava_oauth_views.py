# PR7: canonical location → integrations/strava/oauth.py
# This shim re-exports everything so existing import paths remain valid.
from integrations.strava.oauth import (  # noqa: F401
    LoggedOAuth2Client,
    LoggedStravaOAuth2Adapter,
    oauth2_callback,
    oauth2_login,
    sanitize_oauth_payload,
)
