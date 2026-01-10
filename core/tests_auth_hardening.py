from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase


class AuthHardeningTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coach",
            password="test-pass-123",
        )

    @override_settings(
        USE_COOKIE_AUTH=True,
        COOKIE_AUTH_ACCESS_NAME="mt_access",
        COOKIE_AUTH_REFRESH_NAME="mt_refresh",
        COOKIE_AUTH_SECURE=True,
        COOKIE_AUTH_SAMESITE="Lax",
        COOKIE_AUTH_DOMAIN=None,
    )
    def test_login_sets_cookie_auth_tokens(self):
        response = self.client.post(
            "/api/token/",
            {"username": "coach", "password": "test-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("mt_access", response.cookies)
        self.assertIn("mt_refresh", response.cookies)
        access_cookie = response.cookies["mt_access"]
        refresh_cookie = response.cookies["mt_refresh"]
        self.assertTrue(access_cookie["httponly"])
        self.assertTrue(refresh_cookie["httponly"])
        self.assertTrue(access_cookie["secure"])
        self.assertTrue(refresh_cookie["secure"])
        self.assertEqual(access_cookie["samesite"], "Lax")

    @override_settings(
        USE_COOKIE_AUTH=True,
        COOKIE_AUTH_ACCESS_NAME="mt_access",
        COOKIE_AUTH_REFRESH_NAME="mt_refresh",
        COOKIE_AUTH_SECURE=False,
        COOKIE_AUTH_SAMESITE="Lax",
        COOKIE_AUTH_DOMAIN=None,
    )
    def test_refresh_uses_cookie_and_sets_new_access(self):
        login = self.client.post(
            "/api/token/",
            {"username": "coach", "password": "test-pass-123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("mt_refresh", login.cookies)

        self.client.cookies["mt_refresh"] = login.cookies["mt_refresh"].value
        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("mt_access", response.cookies)

    @override_settings(
        USE_COOKIE_AUTH=True,
        COOKIE_AUTH_ACCESS_NAME="mt_access",
        COOKIE_AUTH_REFRESH_NAME="mt_refresh",
        COOKIE_AUTH_SECURE=False,
        COOKIE_AUTH_SAMESITE="Lax",
        COOKIE_AUTH_DOMAIN=None,
    )
    def test_logout_expires_auth_cookies(self):
        login = self.client.post(
            "/api/token/",
            {"username": "coach", "password": "test-pass-123"},
            format="json",
        )
        self.client.cookies["mt_access"] = login.cookies["mt_access"].value
        self.client.cookies["mt_refresh"] = login.cookies["mt_refresh"].value

        response = self.client.post("/api/token/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies["mt_access"]["max-age"], 0)
        self.assertEqual(response.cookies["mt_refresh"]["max-age"], 0)

    @override_settings(USE_COOKIE_AUTH=False)
    def test_legacy_login_returns_tokens_without_cookies(self):
        response = self.client.post(
            "/api/token/",
            {"username": "coach", "password": "test-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("mt_access", response.cookies)
        self.assertNotIn("mt_refresh", response.cookies)
