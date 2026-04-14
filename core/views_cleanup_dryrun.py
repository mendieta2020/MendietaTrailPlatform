"""
ONE-SHOT temporary endpoint — cleanup dry-run viewer.

DELETE THIS FILE immediately after use.

Security: protected by a long opaque token in the query string.
Usage: GET /ops/cleanup-dryrun/?token=mtp-xK9pQ3vR7wZ2sL8nF5hD4bY1
Returns: text/plain output of `cleanup_prelaunch` in dry-run mode.
"""

import io

from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

# Change this token before deploying if you want extra security.
_VALID_TOKEN = "mtp-xK9pQ3vR7wZ2sL8nF5hD4bY1"


@csrf_exempt
@require_GET
def cleanup_dryrun_view(request):
    token = request.GET.get("token", "")
    if token != _VALID_TOKEN:
        return HttpResponseForbidden("Invalid or missing token.")

    buf = io.StringIO()
    try:
        call_command("cleanup_prelaunch", stdout=buf, stderr=buf)
    except Exception as exc:
        buf.write(f"\n\nERROR: {exc}\n")

    output = buf.getvalue()
    return HttpResponse(output, content_type="text/plain; charset=utf-8")
