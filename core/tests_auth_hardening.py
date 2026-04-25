from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from core.models import Membership, Organization


class AuthHardeningTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coach",
            email="coach@test.com",
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
            {"email": "coach@test.com", "password": "test-pass-123"},
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
            {"email": "coach@test.com", "password": "test-pass-123"},
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
            {"email": "coach@test.com", "password": "test-pass-123"},
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
            {"email": "coach@test.com", "password": "test-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("mt_access", response.cookies)
        self.assertNotIn("mt_refresh", response.cookies)

    @override_settings(USE_COOKIE_AUTH=False)
    def test_no_crash_on_duplicate_email(self):
        """POST /api/token/ returns 200 (not 500) when two users share the same email.
        The auth view must use .filter().first() instead of .get() to avoid
        MultipleObjectsReturned under case-insensitive duplicates."""
        User = get_user_model()
        # Create a second user with the same email (different username to satisfy UNIQUE on username)
        User.objects.create_user(
            username="coach_dup",
            email="coach@test.com",
            password="other-pass-456",
        )
        # The original user (setUp) and this duplicate share "coach@test.com"
        response = self.client.post(
            "/api/token/",
            {"email": "coach@test.com", "password": "test-pass-123"},
            format="json",
        )
        # Must not 500 — returns 200 with the first-created account's token
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)


User = get_user_model()


def _make_org(name, slug=None):
    import uuid
    slug = slug or name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:6]
    return Organization.objects.create(name=name, slug=slug)


class SessionStatusMembershipsTests(APITestCase):
    SESSION_URL = "/api/auth/session/"

    def _login(self, user, password="pass-123"):
        # Ensure user has an email for the email-based login endpoint.
        # Tests that create users without email get a deterministic fallback.
        if not user.email:
            user.email = f"{user.username}@test.local"
            user.save(update_fields=["email"])
        response = self.client.post(
            "/api/token/",
            {"email": user.email, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + response.data["access"]
        )

    def test_session_returns_memberships(self):
        """User with 1 active membership: response includes it with correct fields."""
        user = User.objects.create_user(username="u_single", password="pass-123")
        org = _make_org("Trail Academy")
        Membership.objects.create(user=user, organization=org, role="coach", is_active=True)

        self._login(user)
        response = self.client.get(self.SESSION_URL)

        self.assertEqual(response.status_code, 200)
        self.assertIn("memberships", response.data)
        self.assertEqual(len(response.data["memberships"]), 1)
        m = response.data["memberships"][0]
        self.assertEqual(m["org_id"], org.id)
        self.assertEqual(m["org_name"], org.name)
        self.assertEqual(m["role"], "coach")
        self.assertTrue(m["is_active"])

    def test_session_excludes_inactive_memberships(self):
        """Only active memberships are returned; inactive ones are excluded."""
        user = User.objects.create_user(username="u_inactive", password="pass-123")
        org_active = _make_org("Active Org")
        org_inactive = _make_org("Inactive Org")
        Membership.objects.create(user=user, organization=org_active, role="owner", is_active=True)
        Membership.objects.create(user=user, organization=org_inactive, role="athlete", is_active=False)

        self._login(user)
        response = self.client.get(self.SESSION_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["memberships"]), 1)
        self.assertEqual(response.data["memberships"][0]["org_id"], org_active.id)

    def test_session_no_memberships(self):
        """User with no memberships returns an empty list, not an error."""
        user = User.objects.create_user(username="u_nomem", password="pass-123")

        self._login(user)
        response = self.client.get(self.SESSION_URL)

        self.assertEqual(response.status_code, 200)
        self.assertIn("memberships", response.data)
        self.assertEqual(response.data["memberships"], [])

    def test_session_multiple_orgs(self):
        """User with memberships in 2 orgs: both appear in the response."""
        user = User.objects.create_user(username="u_multi", password="pass-123")
        org1 = _make_org("Org One")
        org2 = _make_org("Org Two")
        Membership.objects.create(user=user, organization=org1, role="owner", is_active=True)
        Membership.objects.create(user=user, organization=org2, role="coach", is_active=True)

        self._login(user)
        response = self.client.get(self.SESSION_URL)

        self.assertEqual(response.status_code, 200)
        org_ids = {m["org_id"] for m in response.data["memberships"]}
        self.assertIn(org1.id, org_ids)
        self.assertIn(org2.id, org_ids)
        self.assertEqual(len(response.data["memberships"]), 2)
