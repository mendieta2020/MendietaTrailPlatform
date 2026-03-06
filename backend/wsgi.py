"""
WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')


def _scrub_sensitive(event, hint):
    """Remove tokens, secrets, and PII from Sentry events before sending."""
    sensitive_keys = {"access_token", "refresh_token", "password", "secret", "authorization"}
    request = event.get("request", {})
    headers = request.get("headers", {})
    for key in list(headers.keys()):
        if key.lower() in sensitive_keys:
            headers[key] = "[Filtered]"
    return event


# Sentry: initialize only when SENTRY_DSN is present.
# No-op in local and CI environments that lack the variable.
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,   # 10% of transactions — adjust in Sentry dashboard
        send_default_pii=False,   # never send cookies, user IPs, or headers automatically
        before_send=_scrub_sensitive,
        environment=os.environ.get("DJANGO_ENV", "production"),
    )

application = get_wsgi_application()
