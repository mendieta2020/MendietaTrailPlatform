# integrations/suunto/ — Suunto Sports Tracking Services integration layer
# Phase 2: FIT ingestion implemented (PR-135).
# Phase 1: OAuth flow (oauth.py). Status: active.
#
# Modules:
#   oauth.py                   — OAuth 2.0 flow helpers
#   client.py                  — Suunto API HTTP client
#   parser.py                  — .FIT binary parser
#   services_suunto_ingest.py  — Idempotent ingestion into CompletedActivity
#   tasks.py                   — Celery fan-out tasks
#
# Notes:
#   Requires SUUNTO_CLIENT_ID, SUUNTO_CLIENT_SECRET, SUUNTO_SUBSCRIPTION_KEY in settings.
#   Requires fitparse in requirements.txt.
