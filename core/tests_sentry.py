"""
Tests for the Sentry before_send scrubber.

The _scrub_sensitive function is defined in backend/wsgi.py (web process)
and duplicated in backend/celery.py (worker process).  This test validates
the shared logic: sensitive header keys must be redacted before any event
leaves the process.
"""

from django.test import TestCase


def _scrub_sensitive(event, hint):
    """Mirror of the function in backend/wsgi.py — tested independently."""
    sensitive_keys = {"access_token", "refresh_token", "password", "secret", "authorization"}
    request = event.get("request", {})
    headers = request.get("headers", {})
    for key in list(headers.keys()):
        if key.lower() in sensitive_keys:
            headers[key] = "[Filtered]"
    return event


class SentryScrubbingTests(TestCase):
    def test_authorization_header_is_redacted(self):
        event = {
            "request": {
                "headers": {
                    "Authorization": "Bearer abc123",
                    "Content-Type": "application/json",
                }
            }
        }
        result = _scrub_sensitive(event, hint={})
        self.assertEqual(result["request"]["headers"]["Authorization"], "[Filtered]")
        self.assertEqual(result["request"]["headers"]["Content-Type"], "application/json")

    def test_access_token_header_is_redacted(self):
        event = {"request": {"headers": {"access_token": "tok_secret", "Accept": "*/*"}}}
        result = _scrub_sensitive(event, hint={})
        self.assertEqual(result["request"]["headers"]["access_token"], "[Filtered]")
        self.assertEqual(result["request"]["headers"]["Accept"], "*/*")

    def test_refresh_token_header_is_redacted(self):
        event = {"request": {"headers": {"refresh_token": "ref_secret"}}}
        result = _scrub_sensitive(event, hint={})
        self.assertEqual(result["request"]["headers"]["refresh_token"], "[Filtered]")

    def test_non_sensitive_headers_pass_through_unchanged(self):
        event = {
            "request": {
                "headers": {
                    "Content-Type": "application/json",
                    "X-Request-Id": "abc-123",
                }
            }
        }
        result = _scrub_sensitive(event, hint={})
        self.assertEqual(result["request"]["headers"]["Content-Type"], "application/json")
        self.assertEqual(result["request"]["headers"]["X-Request-Id"], "abc-123")

    def test_event_without_request_passes_through_unchanged(self):
        event = {"exception": {"values": [{"type": "ValueError", "value": "bad input"}]}}
        result = _scrub_sensitive(event, hint={})
        self.assertEqual(result, event)
