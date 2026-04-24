"""
core/tests_pr186_mp_preapproval_stamp.py — PR-186

Bug #54: AthleteSubscription.mp_preapproval_id stamped on existing records
  Scenario: athlete has AthleteSubscription (no mp_preapproval_id) when
  InvitationAcceptView runs (billing path). MP succeeds but get_or_create
  finds the existing record and ignores defaults. The fix stamps mp_preapproval_id
  post-get_or_create.

Bug #65: stravalib.exc.AccessUnauthorized classified as strava_401
  Before fix: AccessUnauthorized fell through to generic except → logged as
  unexpected_error with reason_code UNEXPECTED_ERROR (masking the real cause).
  After fix: classified as strava_401 with reason_code REFRESH_TOKEN_INVALID.
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteInvitation,
    AthleteSubscription,
    CoachPricingPlan,
    Membership,
    OAuthCredential,
    OrgOAuthCredential,
    Organization,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _org(label: str = "test") -> Organization:
    slug = f"org-{label}-{uuid.uuid4().hex[:6]}"
    return Organization.objects.create(name=f"Org {label}", slug=slug)


def _user(email: str | None = None) -> "User":
    email = email or f"{uuid.uuid4().hex[:8]}@test.com"
    return User.objects.create_user(username=email, email=email, password="TestPass123!")


def _plan(org: Organization, mp_plan_id: str = "mp_plan_test") -> CoachPricingPlan:
    return CoachPricingPlan.objects.create(
        organization=org,
        name="Classic",
        price_ars="38000.00",
        mp_plan_id=mp_plan_id,
        is_active=True,
    )


def _invitation(org: Organization, plan: CoachPricingPlan, email: str) -> AthleteInvitation:
    return AthleteInvitation.objects.create(
        organization=org,
        coach_plan=plan,
        email=email,
        expires_at=timezone.now() + datetime.timedelta(days=30),
    )


# ---------------------------------------------------------------------------
# T1 — Bug #54: preapproval_id stamped on existing sub with null mp_preapproval_id
#
# The production bug: InvitationAcceptView (billing path) calls
# create_coach_athlete_preapproval which returns a real preapproval id.
# If AthleteSubscription already exists (created by onboarding deferred path
# with mp_preapproval_id=None), get_or_create finds it and ignores defaults.
# Fix: stamp mp_preapproval_id after get_or_create when not created.
# ---------------------------------------------------------------------------


class TestBug54PreapprovalIdStamp(TestCase):
    """
    InvitationAcceptView (billing): when AthleteSubscription already exists
    with mp_preapproval_id=None, the fix must stamp the preapproval_id from MP.
    """

    def setUp(self):
        self.client = APIClient()
        self.org = _org("b54")
        self.plan = _plan(self.org, mp_plan_id="mp_plan_b54")
        OrgOAuthCredential.objects.create(
            organization=self.org,
            provider="mercadopago",
            access_token="mp_access_token",
            refresh_token="mp_refresh_token",
            provider_user_id="mp_coach_123",
        )
        self.athlete_user = _user()
        self.invite = _invitation(self.org, self.plan, self.athlete_user.email)

        # Pre-create Athlete + AthleteSubscription WITHOUT mp_preapproval_id,
        # simulating the onboarding deferred path (MP failed on first pass).
        self.athlete = Athlete.objects.create(
            user=self.athlete_user,
            organization=self.org,
            phone_number="+5491100000001",
        )
        self.sub = AthleteSubscription.objects.create(
            athlete=self.athlete,
            coach_plan=self.plan,
            organization=self.org,
            status=AthleteSubscription.Status.PENDING,
            mp_preapproval_id=None,
        )

    @patch(
        "integrations.mercadopago.subscriptions.create_coach_athlete_preapproval",
        return_value={"id": "mp_pa_pr186_test", "init_point": "https://mp.com/pay"},
    )
    def test_t1_preapproval_id_stamped_on_existing_sub(self, mock_mp):
        """
        InvitationAcceptView: MP returns preapproval id → existing sub with
        mp_preapproval_id=None must be stamped by the post-get_or_create fix.
        """
        url = f"/api/billing/invitations/{self.invite.token}/accept/"
        self.client.force_authenticate(self.athlete_user)
        resp = self.client.post(url)

        self.assertIn(
            resp.status_code, (200, 201),
            f"InvitationAcceptView failed: {resp.status_code} {resp.data}",
        )

        self.sub.refresh_from_db()
        self.assertEqual(
            self.sub.mp_preapproval_id,
            "mp_pa_pr186_test",
            "mp_preapproval_id was not stamped on the existing AthleteSubscription",
        )


# ---------------------------------------------------------------------------
# T2 — Bug #65: AccessUnauthorized classified as strava_401, not unexpected_error
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_t2_access_unauthorized_classified_as_strava_401():
    """
    stravalib.exc.AccessUnauthorized raised during token refresh must be logged
    as strava.token.refreshed.strava_401 with reason_code REFRESH_TOKEN_INVALID,
    not as unexpected_error.
    """
    from allauth.socialaccount.models import SocialApp
    from integrations.strava.oauth import refresh_strava_token
    from stravalib import exc as strava_exc

    org = _org("b65")
    coach = _user()
    Membership.objects.create(user=coach, organization=org, role="owner", is_active=True)

    athlete_user = _user()
    from core.models import Alumno
    alumno = Alumno.objects.create(usuario=athlete_user, entrenador=coach)

    SocialApp.objects.create(
        provider="strava", name="Strava", client_id="cid_b65", secret="sec_b65"
    )

    cred = OAuthCredential.objects.create(
        alumno=alumno,
        provider="strava",
        external_user_id="strava_b65",
        access_token="old-access",
        refresh_token="revoked-refresh",
        expires_at=timezone.now() - datetime.timedelta(seconds=120),
    )

    with patch("stravalib.client.Client") as mock_client_cls:
        mock_client_cls.return_value.refresh_access_token.side_effect = (
            strava_exc.AccessUnauthorized("token has been revoked")
        )

        with pytest.raises(Exception):
            with patch("integrations.strava.oauth.logger") as mock_logger:
                refresh_strava_token(cred)

        assert mock_logger.exception.called, "logger.exception was not called"
        call_args = mock_logger.exception.call_args

        event_name = call_args[0][0]
        extra = call_args[1].get("extra", {})

        assert event_name == "strava.token.refreshed.strava_401", (
            f"Expected strava.token.refreshed.strava_401 but got: {event_name}"
        )
        assert extra.get("reason_code") == "REFRESH_TOKEN_INVALID", (
            f"Expected REFRESH_TOKEN_INVALID but got: {extra.get('reason_code')}"
        )
        assert event_name != "strava.token.refreshed.unexpected_error", (
            "AccessUnauthorized must NOT be classified as unexpected_error"
        )
