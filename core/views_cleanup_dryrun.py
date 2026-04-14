"""
ONE-SHOT temporary endpoints — cleanup dry-run + real execute.

DELETE THIS FILE immediately after use.

Security: both endpoints require token=mtp-xK9pQ3vR7wZ2sL8nF5hD4bY1
Execute endpoint also requires confirm=yes.

Usage:
  GET /ops/cleanup-dryrun/?token=mtp-xK9pQ3vR7wZ2sL8nF5hD4bY1
  GET /ops/cleanup-execute/?token=mtp-xK9pQ3vR7wZ2sL8nF5hD4bY1&confirm=yes
"""

import io

from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

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

    return HttpResponse(buf.getvalue(), content_type="text/plain; charset=utf-8")


@csrf_exempt
@require_GET
def cleanup_execute_view(request):
    token = request.GET.get("token", "")
    confirm = request.GET.get("confirm", "")

    if token != _VALID_TOKEN:
        return HttpResponseForbidden("Invalid or missing token.")

    if confirm != "yes":
        return HttpResponseForbidden("Missing confirm=yes parameter.")

    buf = io.StringIO()
    try:
        call_command("cleanup_prelaunch", no_dry_run=True, force=True, stdout=buf, stderr=buf)
    except Exception as exc:
        buf.write(f"\n\nERROR: {exc}\n")

    return HttpResponse(buf.getvalue(), content_type="text/plain; charset=utf-8")
