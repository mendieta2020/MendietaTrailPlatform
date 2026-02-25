"""
core/landing_views.py — PR16

Minimal institutional landing page at GET /.
- No auth required (plain Django view, not DRF).
- No templates — inline HTML to avoid any template-loading dependency.
- No business data exposed — purely informational.
"""

from django.http import HttpResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET


@require_GET
@cache_control(max_age=60, public=True)
def landing(request):
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MendietaTrailPlatform API</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; color: #222; }
    h1   { font-size: 1.5rem; }
    ul   { line-height: 2; }
    a    { color: #0070f3; }
  </style>
</head>
<body>
  <h1>MendietaTrailPlatform API is running</h1>
  <p>Backend service is operational.</p>
  <ul>
    <li><a href="/api/">API Root</a></li>
    <li><a href="/admin/">Admin</a></li>
    <li><a href="/healthz">Health Check</a></li>
  </ul>
</body>
</html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")
