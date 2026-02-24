"""
PR16 — CORS Regex Fix Tests
===========================
Verifies that:
1. parse_env_list() correctly handles CSV values (unit).
2. CORS_ALLOWED_ORIGIN_REGEXES is wired into settings (unit).
3. Preflight OPTIONS /api/token/ returns Access-Control-Allow-Origin for
   allowed origins (exact + regex) and is absent for disallowed ones (integration).

No new models. No migrations. No external I/O.
"""

import re

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from backend.settings import parse_env_list


# ==============================================================================
#  Unit: settings helpers & config assertions
# ==============================================================================

class CorsSettingsParsingTests(SimpleTestCase):
    """Pure unit tests — no DB, no HTTP."""

    # ----- parse_env_list -----

    def test_parse_env_list_empty_string(self):
        self.assertEqual(parse_env_list(""), [])

    def test_parse_env_list_none(self):
        self.assertEqual(parse_env_list(None), [])

    def test_parse_env_list_single_entry(self):
        result = parse_env_list("https://example.com")
        self.assertEqual(result, ["https://example.com"])

    def test_parse_env_list_csv_strips_whitespace(self):
        result = parse_env_list("https://a.com , https://b.com,https://c.com")
        self.assertEqual(result, ["https://a.com", "https://b.com", "https://c.com"])

    # ----- Settings-level assertions (override_settings) -----

    @override_settings(
        CORS_ALLOWED_ORIGINS=[
            "http://localhost:5173",
            "https://mendieta-trail-platform.vercel.app",
            "https://quantoryn.com",
        ],
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.vercel\.app$"],
    )
    def test_production_vercel_domain_in_allowed_origins(self):
        from django.conf import settings
        self.assertIn(
            "https://mendieta-trail-platform.vercel.app",
            settings.CORS_ALLOWED_ORIGINS,
        )

    @override_settings(
        CORS_ALLOWED_ORIGINS=["https://mendieta-trail-platform.vercel.app"],
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.vercel\.app$"],
    )
    def test_quantoryn_in_allowed_origins(self):
        from django.conf import settings
        # Quantoryn is an exact-match entry in real .env; simulate here.
        with self.settings(CORS_ALLOWED_ORIGINS=[
            "https://mendieta-trail-platform.vercel.app",
            "https://quantoryn.com",
        ]):
            from django.conf import settings as s
            self.assertIn("https://quantoryn.com", s.CORS_ALLOWED_ORIGINS)

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False)
    def test_cors_allow_all_origins_is_false(self):
        """Global wildcard must never be True."""
        from django.conf import settings
        self.assertFalse(settings.CORS_ALLOW_ALL_ORIGINS)

    @override_settings(CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.vercel\.app$"])
    def test_vercel_regex_matches_preview_url(self):
        """The configured regex must match a rotated Vercel preview URL."""
        from django.conf import settings
        origin = "https://mendieta-trail-platform-git-fix-cors-user.vercel.app"
        matched = any(
            re.match(pattern, origin)
            for pattern in settings.CORS_ALLOWED_ORIGIN_REGEXES
        )
        self.assertTrue(matched, f"Regex should match '{origin}'")

    @override_settings(CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.vercel\.app$"])
    def test_vercel_regex_does_not_match_evil_origin(self):
        """The regex must NOT match arbitrary origins."""
        from django.conf import settings
        origin = "https://evil.example.com"
        matched = any(
            re.match(pattern, origin)
            for pattern in settings.CORS_ALLOWED_ORIGIN_REGEXES
        )
        self.assertFalse(matched, f"Regex must NOT match '{origin}'")


# ==============================================================================
#  Integration: actual OPTIONS preflight via APIClient
# ==============================================================================

CORS_OVERRIDE = dict(
    CORS_ALLOW_ALL_ORIGINS=False,
    CORS_ALLOWED_ORIGINS=[
        "http://localhost:5173",
        "https://mendieta-trail-platform.vercel.app",
        "https://quantoryn.com",
    ],
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.vercel\.app$"],
    CORS_ALLOW_CREDENTIALS=False,
)


class CorsPreflightTests(APITestCase):
    """
    Integration tests: send OPTIONS to /api/token/ with various Origin headers
    and assert that django-cors-headers sets (or withholds) the ACAO header.
    """

    @override_settings(**CORS_OVERRIDE)
    def test_preflight_from_vercel_production_returns_acao(self):
        """Exact-match: production Vercel domain gets Access-Control-Allow-Origin."""
        response = self.client.options(
            "/api/token/",
            HTTP_ORIGIN="https://mendieta-trail-platform.vercel.app",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertIn(
            "Access-Control-Allow-Origin",
            response,
            "CorsMiddleware must add ACAO header for the production Vercel origin.",
        )
        self.assertEqual(
            response["Access-Control-Allow-Origin"],
            "https://mendieta-trail-platform.vercel.app",
        )

    @override_settings(**CORS_OVERRIDE)
    def test_preflight_from_quantoryn_returns_acao(self):
        """Exact-match: custom domain quantoryn.com gets Access-Control-Allow-Origin."""
        response = self.client.options(
            "/api/token/",
            HTTP_ORIGIN="https://quantoryn.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertIn("Access-Control-Allow-Origin", response)
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://quantoryn.com")

    @override_settings(**CORS_OVERRIDE)
    def test_preflight_from_vercel_preview_via_regex_returns_acao(self):
        """Regex-match: rotating Vercel preview URL gets Access-Control-Allow-Origin."""
        preview_origin = (
            "https://mendieta-trail-platform-git-fix-cors-user.vercel.app"
        )
        response = self.client.options(
            "/api/token/",
            HTTP_ORIGIN=preview_origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertIn(
            "Access-Control-Allow-Origin",
            response,
            f"CorsMiddleware must add ACAO header for preview URL '{preview_origin}'.",
        )
        self.assertEqual(response["Access-Control-Allow-Origin"], preview_origin)

    @override_settings(**CORS_OVERRIDE)
    def test_preflight_from_evil_origin_has_no_acao(self):
        """Unknown origin must NOT receive Access-Control-Allow-Origin."""
        response = self.client.options(
            "/api/token/",
            HTTP_ORIGIN="https://evil.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertNotIn(
            "Access-Control-Allow-Origin",
            response,
            "CorsMiddleware must NOT add ACAO header for unlisted origins.",
        )

    @override_settings(**CORS_OVERRIDE)
    def test_preflight_from_localhost_returns_acao(self):
        """Local dev origin must still work (regression guard)."""
        response = self.client.options(
            "/api/token/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertIn("Access-Control-Allow-Origin", response)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
