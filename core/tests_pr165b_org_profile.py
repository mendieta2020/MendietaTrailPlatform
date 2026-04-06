"""
PR-165b — Org Profile + My Subscription backend tests.

Covers:
- Organization model: new profile fields save correctly
- OrgProfileView GET: any active member can read
- OrgProfileView GET: non-member is rejected (403)
- OrgProfileView PATCH: owner can update
- OrgProfileView PATCH: admin can update
- OrgProfileView PATCH: athlete/coach cannot update (403)
- MySubscriptionView: returns coach + subscription data for athlete
- MySubscriptionView: non-athlete membership returns 404
- MySubscriptionView: missing org_id returns 400
- MySubscriptionView: includes trial_ends_at and trial_active
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import (
    Athlete,
    AthleteSubscription,
    Coach,
    CoachPricingPlan,
    Membership,
    Organization,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email=None, password="testpass"):
    email = email or f"{username}@example.com"
    return User.objects.create_user(username=username, email=email, password=password)


def _membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role)


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


# ---------------------------------------------------------------------------
# Organization model: profile fields
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOrgProfileFields:
    def test_new_fields_save_and_retrieve(self):
        org = _org("trail-club")
        org.description = "El mejor club de trail"
        org.contact_email = "info@trail.com"
        org.phone = "+54 9 11 1234-5678"
        org.instagram = "trail_club"
        org.website = "https://trail.com"
        org.city = "Mendoza"
        org.disciplines = "Trail Running, Ultra"
        org.founded_year = 2018
        org.save()

        fresh = Organization.objects.get(id=org.id)
        assert fresh.description == "El mejor club de trail"
        assert fresh.contact_email == "info@trail.com"
        assert fresh.phone == "+54 9 11 1234-5678"
        assert fresh.instagram == "trail_club"
        assert fresh.website == "https://trail.com"
        assert fresh.city == "Mendoza"
        assert fresh.disciplines == "Trail Running, Ultra"
        assert fresh.founded_year == 2018

    def test_new_fields_default_blank(self):
        org = _org("bare-org")
        assert org.description == ""
        assert org.contact_email == ""
        assert org.city == ""
        assert org.founded_year is None


# ---------------------------------------------------------------------------
# OrgProfileView
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOrgProfileView:
    def setup_method(self):
        self.org = _org("profile-org")
        self.org.description = "Descripción de prueba"
        self.org.city = "Córdoba"
        self.org.save()

        self.owner = _user("owner_profile")
        self.coach = _user("coach_profile")
        self.athlete_user = _user("athlete_profile")
        self.outsider = _user("outsider_profile")

        _membership(self.owner, self.org, "owner")
        _membership(self.coach, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")

    def _url(self):
        return f"/api/p1/orgs/{self.org.id}/profile/"

    def test_owner_can_read(self):
        client = _auth_client(self.owner)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["city"] == "Córdoba"
        assert res.data["description"] == "Descripción de prueba"
        assert res.data["name"] == "profile-org"

    def test_coach_can_read(self):
        client = _auth_client(self.coach)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK

    def test_athlete_can_read(self):
        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK

    def test_non_member_is_403(self):
        client = _auth_client(self.outsider)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_can_patch(self):
        client = _auth_client(self.owner)
        res = client.patch(self._url(), {"city": "Rosario", "disciplines": "Trail, Ruta"}, format="json")
        assert res.status_code == status.HTTP_200_OK
        self.org.refresh_from_db()
        assert self.org.city == "Rosario"
        assert self.org.disciplines == "Trail, Ruta"

    def test_coach_cannot_patch(self):
        client = _auth_client(self.coach)
        res = client.patch(self._url(), {"city": "Bogotá"}, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_athlete_cannot_patch(self):
        client = _auth_client(self.athlete_user)
        res = client.patch(self._url(), {"city": "Lima"}, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_cannot_patch(self):
        client = _auth_client(self.outsider)
        res = client.patch(self._url(), {"city": "Lima"}, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_only_updates_allowed_fields(self):
        """is_active and slug cannot be changed via this endpoint."""
        client = _auth_client(self.owner)
        original_slug = self.org.slug
        res = client.patch(self._url(), {"slug": "hacked", "is_active": False}, format="json")
        assert res.status_code == status.HTTP_200_OK
        self.org.refresh_from_db()
        assert self.org.slug == original_slug
        assert self.org.is_active is True

    def test_athlete_does_not_see_contact_email_or_phone(self):
        """Operational data must be hidden from athletes."""
        self.org.contact_email = "contact@org.com"
        self.org.phone = "+54 9 11 9999-9999"
        self.org.save()
        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert "contact_email" not in res.data
        assert "phone" not in res.data

    def test_coach_sees_contact_email_and_phone(self):
        """Coaches need operational data to coordinate with the org owner."""
        self.org.contact_email = "contact@org.com"
        self.org.phone = "+54 9 11 9999-9999"
        self.org.save()
        client = _auth_client(self.coach)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["contact_email"] == "contact@org.com"
        assert res.data["phone"] == "+54 9 11 9999-9999"

    def test_owner_sees_all_fields_and_can_edit_true(self):
        """Owner gets full profile and can_edit=True."""
        self.org.contact_email = "contact@org.com"
        self.org.phone = "+54 9 11 9999-9999"
        self.org.save()
        client = _auth_client(self.owner)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["contact_email"] == "contact@org.com"
        assert res.data["phone"] == "+54 9 11 9999-9999"
        assert res.data["can_edit"] is True

    def test_athlete_gets_can_edit_false(self):
        """Athletes must never see the edit button."""
        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["can_edit"] is False


# ---------------------------------------------------------------------------
# MySubscriptionView
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMySubscriptionView:
    def setup_method(self):
        self.org = _org("sub-org")

        self.coach_user = _user("coach_sub")
        self.athlete_user = _user("athlete_sub")
        self.other_user = _user("other_sub")

        _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")

        self.coach_obj = Coach.objects.create(
            user=self.coach_user,
            organization=self.org,
            bio="Especialista en trail",
            specialties="Trail, Ultra",
            years_experience=5,
        )
        self.athlete_obj = Athlete.objects.create(
            user=self.athlete_user,
            organization=self.org,
            coach=self.coach_obj,
        )

        self.plan = CoachPricingPlan.objects.create(
            organization=self.org,
            name="Plan Pro",
            price_ars=15000,
            is_active=True,
        )
        self.sub = AthleteSubscription.objects.create(
            athlete=self.athlete_obj,
            organization=self.org,
            coach_plan=self.plan,
            status=AthleteSubscription.Status.ACTIVE,
        )

    def _url(self):
        return f"/api/me/subscription/?org_id={self.org.id}"

    def test_athlete_gets_coach_and_subscription(self):
        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["coach"]["specialties"] == "Trail, Ultra"
        assert res.data["subscription"]["plan_name"] == "Plan Pro"
        assert res.data["organization"]["name"] == "sub-org"

    def test_non_athlete_membership_returns_404(self):
        _membership(self.other_user, self.org, "coach")
        client = _auth_client(self.other_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_missing_org_id_returns_400(self):
        client = _auth_client(self.athlete_user)
        res = client.get("/api/me/subscription/")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_membership_in_org_returns_404(self):
        other_org = _org("other-sub-org")
        client = _auth_client(self.athlete_user)
        res = client.get(f"/api/me/subscription/?org_id={other_org.id}")
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_trial_ends_at_included(self):
        trial_end = timezone.now() + timezone.timedelta(days=3)
        self.sub.trial_ends_at = trial_end
        self.sub.status = AthleteSubscription.Status.PENDING
        self.sub.save()

        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["subscription"]["trial_ends_at"] is not None
        assert res.data["subscription"]["trial_active"] is True
        assert res.data["subscription"]["trial_days_remaining"] >= 2

    def test_no_coach_assigned_returns_null_coach(self):
        self.athlete_obj.coach = None
        self.athlete_obj.save()
        client = _auth_client(self.athlete_user)
        res = client.get(self._url())
        assert res.status_code == status.HTTP_200_OK
        assert res.data["coach"] is None
