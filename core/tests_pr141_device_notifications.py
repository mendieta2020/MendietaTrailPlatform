"""
PR-141 — Athlete device status in roster + smart notification system.

Tests:
 1.  GET /api/athlete/device-status/ — no device → show_prompt=True
 2.  GET /api/athlete/device-status/ — with device → show_prompt=False, has_device=True
 3.  GET /api/athlete/device-status/ — dismissed → show_prompt=False even without device
 4.  POST /api/athlete/device-preference/dismiss/ — sets dismissed=True
 5.  POST /api/athlete/device-preference/reactivate/ — resets dismissed=False
 6.  POST /api/athlete/device-preference/dismiss/ — coach calling → 403
 7.  GET /api/athlete/notifications/ — returns only this athlete's unread notifications
 8.  POST /api/athlete/notifications/{id}/mark-read/ — wrong athlete → 403/404
 9.  POST /api/coach/roster/{id}/notify-device/ — coach creates notification for athlete
10.  POST /api/coach/roster/{id}/notify-device/ — duplicate prevention
11.  POST /api/coach/roster/{id}/notify-device/ — athlete from different org → 404
12.  Roster GET — athlete devices field present and organization-scoped
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    AthleteDevicePreference,
    AthleteNotification,
    Membership,
    OAuthIntegrationStatus,
    Organization,
)

User = get_user_model()

DEVICE_STATUS_URL = "/api/athlete/device-status/"
DISMISS_URL = "/api/athlete/device-preference/dismiss/"
REACTIVATE_URL = "/api/athlete/device-preference/reactivate/"
NOTIFICATIONS_URL = "/api/athlete/notifications/"


def _mark_read_url(pk):
    return f"/api/athlete/notifications/{pk}/mark-read/"


def _notify_url(membership_id):
    return f"/api/coach/roster/{membership_id}/notify-device/"


ROSTER_URL_TPL = "/api/p1/orgs/{org_id}/roster/athletes/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(name=None):
    slug = uuid.uuid4().hex[:12]
    return Organization.objects.create(name=name or f"Org-{slug}", slug=slug)


def _make_user():
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    return User.objects.create_user(username=email, email=email, password="pass1234")


def _make_membership(user, org, role=Membership.Role.ATHLETE):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=True
    )


def _make_athlete_record(user, org):
    """Create P1 Athlete record for the user in org."""
    return Athlete.objects.create(user=user, organization=org, is_active=True)


def _make_alumno(user):
    """Create legacy Alumno linked to user (needed for OAuthIntegrationStatus check)."""
    return Alumno.objects.create(
        usuario=user,
        nombre=user.first_name or "Test",
        apellido=user.last_name or "Athlete",
        email=user.email,
    )


def _connect_device(alumno, provider="strava"):
    """Mark an OAuthIntegrationStatus as connected."""
    return OAuthIntegrationStatus.objects.create(
        alumno=alumno,
        provider=provider,
        connected=True,
    )


# ---------------------------------------------------------------------------
# Test 1: GET device-status — no device → show_prompt=True
# ---------------------------------------------------------------------------

class DeviceStatusNoDeviceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        _make_membership(self.user, self.org)

    def test_no_device_returns_show_prompt_true(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(DEVICE_STATUS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_device"])
        self.assertTrue(res.data["show_prompt"])
        self.assertFalse(res.data["dismissed"])


# ---------------------------------------------------------------------------
# Test 2: GET device-status — with device → show_prompt=False, has_device=True
# ---------------------------------------------------------------------------

class DeviceStatusWithDeviceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        _make_membership(self.user, self.org)
        alumno = _make_alumno(self.user)
        _connect_device(alumno)

    def test_with_device_show_prompt_false(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(DEVICE_STATUS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_device"])
        self.assertFalse(res.data["show_prompt"])


# ---------------------------------------------------------------------------
# Test 3: GET device-status — dismissed → show_prompt=False without device
# ---------------------------------------------------------------------------

class DeviceStatusDismissedTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        _make_membership(self.user, self.org)
        # No device; but preference is dismissed
        AthleteDevicePreference.objects.create(
            organization=self.org,
            athlete=self.user,
            dismissed=True,
            dismissed_reason="no_device",
        )

    def test_dismissed_hides_prompt_even_without_device(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(DEVICE_STATUS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_device"])
        self.assertFalse(res.data["show_prompt"])
        self.assertTrue(res.data["dismissed"])
        self.assertEqual(res.data["dismissed_reason"], "no_device")


# ---------------------------------------------------------------------------
# Test 4: POST dismiss — sets dismissed=True
# ---------------------------------------------------------------------------

class DismissPreferenceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        _make_membership(self.user, self.org)

    def test_dismiss_creates_preference_dismissed(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post(DISMISS_URL, {"reason": "no_device"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["ok"])
        pref = AthleteDevicePreference.objects.get(athlete=self.user)
        self.assertTrue(pref.dismissed)
        self.assertEqual(pref.dismissed_reason, "no_device")

    def test_dismiss_idempotent_second_call(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(DISMISS_URL, {"reason": "no_device"}, format="json")
        res = self.client.post(DISMISS_URL, {"reason": "no_device"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Only one preference record
        self.assertEqual(AthleteDevicePreference.objects.filter(athlete=self.user).count(), 1)


# ---------------------------------------------------------------------------
# Test 5: POST reactivate — resets dismissed=False
# ---------------------------------------------------------------------------

class ReactivatePreferenceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.user = _make_user()
        _make_membership(self.user, self.org)
        AthleteDevicePreference.objects.create(
            organization=self.org,
            athlete=self.user,
            dismissed=True,
            dismissed_reason="no_device",
        )

    def test_reactivate_clears_dismissed(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post(REACTIVATE_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["ok"])
        pref = AthleteDevicePreference.objects.get(athlete=self.user)
        self.assertFalse(pref.dismissed)
        self.assertIsNone(pref.dismissed_reason)
        self.assertIsNone(pref.dismissed_at)


# ---------------------------------------------------------------------------
# Test 6: POST dismiss — coach calling → 403
# ---------------------------------------------------------------------------

class DismissCoachForbiddenTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.coach = _make_user()
        _make_membership(self.coach, self.org, role=Membership.Role.COACH)

    def test_coach_cannot_dismiss_athlete_preference(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.post(DISMISS_URL, {"reason": "no_device"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Test 7: GET notifications — returns only this athlete's unread notifications
# ---------------------------------------------------------------------------

class NotificationListTenancyTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org1 = _make_org()
        self.org2 = _make_org("Org2")
        self.athlete1 = _make_user()
        self.athlete2 = _make_user()
        _make_membership(self.athlete1, self.org1)
        _make_membership(self.athlete2, self.org2)

        # Notification for athlete1 in org1
        self.n1 = AthleteNotification.objects.create(
            organization=self.org1,
            recipient=self.athlete1,
            notification_type="device_connect",
        )
        # Notification for athlete2 in org2
        AthleteNotification.objects.create(
            organization=self.org2,
            recipient=self.athlete2,
            notification_type="device_connect",
        )

    def test_returns_only_own_unread_notifications(self):
        self.client.force_authenticate(user=self.athlete1)
        res = self.client.get(NOTIFICATIONS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [n["id"] for n in res.data]
        self.assertIn(self.n1.id, ids)
        self.assertEqual(len(ids), 1)

    def test_read_notifications_not_returned(self):
        self.n1.read = True
        self.n1.save()
        self.client.force_authenticate(user=self.athlete1)
        res = self.client.get(NOTIFICATIONS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)


# ---------------------------------------------------------------------------
# Test 8: POST mark-read — wrong athlete → 403/404
# ---------------------------------------------------------------------------

class MarkReadWrongAthleteTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.athlete1 = _make_user()
        self.athlete2 = _make_user()
        _make_membership(self.athlete1, self.org)
        _make_membership(self.athlete2, self.org)

        self.notification = AthleteNotification.objects.create(
            organization=self.org,
            recipient=self.athlete1,
            notification_type="device_connect",
        )

    def test_wrong_athlete_cannot_mark_read(self):
        self.client.force_authenticate(user=self.athlete2)
        res = self.client.post(_mark_read_url(self.notification.id))
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_correct_athlete_can_mark_read(self):
        self.client.force_authenticate(user=self.athlete1)
        res = self.client.post(_mark_read_url(self.notification.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.read)


# ---------------------------------------------------------------------------
# Test 9: POST notify-device — coach creates notification for athlete in org
# ---------------------------------------------------------------------------

class CoachNotifyAthleteTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.coach = _make_user()
        self.athlete_user = _make_user()
        _make_membership(self.coach, self.org, role=Membership.Role.COACH)
        self.athlete_membership = _make_membership(self.athlete_user, self.org)

    def test_coach_creates_device_notification(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.post(_notify_url(self.athlete_membership.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["ok"])
        self.assertTrue(res.data["created"])
        self.assertEqual(
            AthleteNotification.objects.filter(
                recipient=self.athlete_user,
                notification_type="device_connect",
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# Test 10: POST notify-device — duplicate prevention
# ---------------------------------------------------------------------------

class CoachNotifyDuplicateTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.coach = _make_user()
        self.athlete_user = _make_user()
        _make_membership(self.coach, self.org, role=Membership.Role.COACH)
        self.athlete_membership = _make_membership(self.athlete_user, self.org)

    def test_duplicate_notification_not_created(self):
        self.client.force_authenticate(user=self.coach)
        # First call — creates
        res1 = self.client.post(_notify_url(self.athlete_membership.id))
        self.assertTrue(res1.data["created"])
        # Second call — duplicate guard
        res2 = self.client.post(_notify_url(self.athlete_membership.id))
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data["created"])
        self.assertEqual(
            AthleteNotification.objects.filter(
                recipient=self.athlete_user,
                notification_type="device_connect",
                read=False,
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# Test 11: POST notify-device — athlete from different org → 404
# ---------------------------------------------------------------------------

class CoachNotifyWrongOrgTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org1 = _make_org()
        self.org2 = _make_org("Org2")
        self.coach = _make_user()
        self.athlete_user = _make_user()
        _make_membership(self.coach, self.org1, role=Membership.Role.COACH)
        # Athlete is in org2, NOT org1
        self.athlete_membership = _make_membership(self.athlete_user, self.org2)

    def test_cross_org_membership_returns_404(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.post(_notify_url(self.athlete_membership.id))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Test 12: Roster GET — devices field present and org-scoped
# ---------------------------------------------------------------------------

class RosterDevicesFieldTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = _make_org()
        self.owner = _make_user()
        self.athlete_user = _make_user()
        _make_membership(self.owner, self.org, role=Membership.Role.OWNER)
        _make_membership(self.athlete_user, self.org)
        _make_athlete_record(self.athlete_user, self.org)

    def test_roster_includes_devices_field(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(ROSTER_URL_TPL.format(org_id=self.org.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertTrue(len(results) > 0)
        first = results[0]
        self.assertIn("devices", first)
        self.assertIsInstance(first["devices"], list)

    def test_roster_includes_membership_id_field(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(ROSTER_URL_TPL.format(org_id=self.org.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        first = results[0]
        self.assertIn("membership_id", first)
        # membership_id must match the athlete's active membership
        expected_membership = Membership.objects.get(
            user=self.athlete_user, organization=self.org, role="athlete"
        )
        self.assertEqual(first["membership_id"], expected_membership.id)

    def test_roster_devices_field_is_org_scoped(self):
        """An athlete in org2 with a device must not pollute org1 roster."""
        org2 = _make_org("Org2")
        other_user = _make_user()
        _make_membership(other_user, org2)
        _make_athlete_record(other_user, org2)
        # Give other_user a connected device
        alumno = _make_alumno(other_user)
        _connect_device(alumno)

        # Org1 roster: athlete_user has no device → devices should be []
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(ROSTER_URL_TPL.format(org_id=self.org.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        athlete_row = next(r for r in results if r["user_id"] == self.athlete_user.id)
        self.assertEqual(athlete_row["devices"], [])
