# integrations/strava/ — all Strava-specific helper code (PR7)
# Modules:
#   normalizer.py  — normalize Strava activity payloads to business types
#   mapper.py      — map stravalib Activity objects to Actividad model dicts
#   elevation.py   — elevation smoothing + loss calculation from altitude streams
#   oauth.py       — logged OAuth2 views / adapter overriding allauth defaults
