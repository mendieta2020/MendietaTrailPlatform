"""
core/tests_static_config.py — PR16 regression guard.

These tests prevent silent removal of WhiteNoise middleware or storage,
which would immediately break /static/* in Railway (DEBUG=False + Gunicorn).
"""

from django.conf import settings
from django.test import RequestFactory, TestCase

from core.landing_views import landing


class WhiteNoiseConfigTest(TestCase):
    """Guard: WhiteNoise must stay wired correctly or /static/* breaks in prod."""

    # ------------------------------------------------------------------
    # 1. Middleware order
    # ------------------------------------------------------------------
    def test_whitenoise_middleware_in_middleware(self):
        """WhiteNoiseMiddleware must be immediately after SecurityMiddleware."""
        mw = list(settings.MIDDLEWARE)
        security_idx = mw.index("django.middleware.security.SecurityMiddleware")
        whitenoise_idx = mw.index("whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertEqual(
            whitenoise_idx,
            security_idx + 1,
            "WhiteNoiseMiddleware must immediately follow SecurityMiddleware "
            "(required by WhiteNoise docs — inserting between them breaks nothing).",
        )

    # ------------------------------------------------------------------
    # 2. Static storage backend
    # ------------------------------------------------------------------
    def test_staticfiles_storage_is_whitenoise(self):
        """CompressedManifestStaticFilesStorage enables gzip + hash fingerprinting for prod."""
        expected = "whitenoise.storage.CompressedManifestStaticFilesStorage"
        # Django 4.2+ uses STORAGES dict; fallback to legacy STATICFILES_STORAGE.
        storages = getattr(settings, "STORAGES", {})
        if storages:
            actual = storages.get("staticfiles", {}).get("BACKEND", "")
        else:
            actual = getattr(settings, "STATICFILES_STORAGE", "")
        self.assertEqual(
            actual,
            expected,
            f"Expected staticfiles backend to be {expected!r}, got {actual!r}.",
        )

    # ------------------------------------------------------------------
    # 3. Landing page smoke test
    # ------------------------------------------------------------------
    def test_landing_returns_200(self):
        """GET / must return 200 and identify the platform (institutional confidence)."""
        factory = RequestFactory()
        request = factory.get("/")
        response = landing(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"MendietaTrailPlatform", response.content)
