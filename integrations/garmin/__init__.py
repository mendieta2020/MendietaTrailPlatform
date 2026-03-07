# integrations/garmin/ — Garmin Connect integration layer
# Status: STUB — not yet implemented.
#
# Modules (to be populated when vendor access is granted):
#   provider.py  — GarminProviderAdapter (OAuth 1.0a flow + activity polling)
#
# Notes:
#   Garmin uses OAuth 1.0a (not 2.0). Implementation requires
#   requests-oauthlib and Garmin Connect API credentials.
#   Activity sync uses polling; no public webhook API is available.
