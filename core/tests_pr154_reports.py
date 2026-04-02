"""
core/tests_pr154_reports.py

Tests for PR-154: AthleteReport — shareable training report (WhatsApp + email).

8 targeted tests covering:
  - Report creation returns token + URL
  - Tenancy validation (can't create for athlete in different org)
  - Public report page: valid token returns 200
  - Public report page: expired token returns 404
  - Public report page: invalid token returns 404
  - view_count increments on each visit
  - Email endpoint rejects invalid email
  - Snapshot contains all expected fields
"""

import pytest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AthleteReport, Membership, Organization

User = get_user_model()


def _make_org(name="TestOrg"):
    import uuid
    slug = uuid.uuid4().hex[:20]
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username, first="", last=""):
    u = User.objects.create_user(username=username, password="pass", first_name=first, last_name=last)
    return u


def _make_membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role)


def _make_report(org, athlete_user, coach_user, membership, expired=False):
    now = timezone.now()
    expires_at = (now - timedelta(hours=1)) if expired else (now + timedelta(days=7))
    return AthleteReport.objects.create(
        token="testtokenabcdef1234" if not expired else "expiredtoken1234567",
        organization=org,
        athlete_user=athlete_user,
        coach_user=coach_user,
        membership=membership,
        period_days=90,
        coach_message="Excellent work!",
        snapshot={
            "athlete_name": "Test Athlete",
            "coach_name": "Test Coach",
            "coach_message": "Excellent work!",
            "period_days": 90,
            "kpis": {"ctl": 120.0, "atl": 130.0, "tsb": -10.0, "readiness_score": 55, "readiness_label": "OK",
                     "ramp_rate_7d": 3.0, "ramp_rate_28d": 2.0, "acwr": 1.08, "gap_avg_formatted": "4:30/km"},
            "pmc_days": [],
            "projection": [],
            "volume_by_sport": {"TRAIL": {"distance_km": 200, "duration_minutes": 1200, "elevation_gain_m": 4000, "calories_kcal": 12000, "sessions_count": 20}},
            "compliance_pct": 85,
            "wellness_avg": 3.8,
        },
        expires_at=expires_at,
    )


@pytest.mark.django_db
class TestCreateReport:
    def test_create_report_returns_token_and_url(self):
        """POST creates a report with a valid token and shareable URL."""
        org = _make_org()
        coach = _make_user("coach1")
        athlete = _make_user("athlete1")
        coach_m = _make_membership(coach, org, Membership.Role.OWNER)
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)

        client = APIClient()
        client.force_authenticate(user=coach)

        res = client.post(
            f"/api/coach/athletes/{athlete_m.pk}/report/",
            {"period_days": 90, "coach_message": "Great job!"},
            format="json",
        )

        assert res.status_code == 201
        data = res.json()
        assert "token" in data
        assert len(data["token"]) == 32  # UUID hex
        assert "/report/" in data["url"]
        assert "expires_at" in data
        assert "preview" in data
        assert "athlete_name" in data["preview"]

    def test_create_report_tenancy_validation(self):
        """Coach cannot create report for athlete in a different organization."""
        org1 = _make_org("Org1")
        org2 = _make_org("Org2")
        coach = _make_user("coach2")
        athlete = _make_user("athlete2")
        _make_membership(coach, org1, Membership.Role.OWNER)
        athlete_m2 = _make_membership(athlete, org2, Membership.Role.ATHLETE)

        client = APIClient()
        client.force_authenticate(user=coach)

        res = client.post(
            f"/api/coach/athletes/{athlete_m2.pk}/report/",
            {"period_days": 90},
            format="json",
        )
        # Must fail: athlete belongs to org2, coach belongs to org1
        assert res.status_code in (403, 404)

    def test_snapshot_contains_expected_fields(self):
        """Report snapshot must include kpis, volume_by_sport, pmc_days, projection."""
        org = _make_org("SnapOrg")
        coach = _make_user("snap_coach")
        athlete = _make_user("snap_athlete")
        _make_membership(coach, org, Membership.Role.OWNER)
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)

        client = APIClient()
        client.force_authenticate(user=coach)
        client.post(f"/api/coach/athletes/{athlete_m.pk}/report/", {"period_days": 30}, format="json")

        report = AthleteReport.objects.filter(organization=org).first()
        assert report is not None
        snap = report.snapshot
        assert "kpis" in snap
        assert "volume_by_sport" in snap
        assert "pmc_days" in snap
        assert "projection" in snap
        assert "athlete_name" in snap
        assert "coach_name" in snap
        # kpis must have the required fields
        kpis = snap["kpis"]
        for field in ("ctl", "atl", "tsb", "readiness_score", "ramp_rate_7d"):
            assert field in kpis, f"Missing kpi field: {field}"


@pytest.mark.django_db
class TestPublicReportPage:
    def test_valid_token_returns_200(self):
        """GET /report/<valid_token>/ returns 200 for non-expired report."""
        org = _make_org("PubOrg")
        coach = _make_user("pub_coach")
        athlete = _make_user("pub_athlete")
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)
        report = _make_report(org, athlete, coach, athlete_m)

        client = APIClient()
        res = client.get(f"/report/{report.token}/")

        assert res.status_code == 200

    def test_expired_token_returns_404(self):
        """GET /report/<expired_token>/ returns 404."""
        org = _make_org("ExpOrg")
        coach = _make_user("exp_coach")
        athlete = _make_user("exp_athlete")
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)
        report = _make_report(org, athlete, coach, athlete_m, expired=True)

        client = APIClient()
        res = client.get(f"/report/{report.token}/")

        assert res.status_code == 404

    def test_invalid_token_returns_404(self):
        """GET /report/<random_token>/ returns 404 for unknown token."""
        client = APIClient()
        res = client.get("/report/doesnotexisttoken12345/")
        assert res.status_code == 404

    def test_view_count_increments_on_access(self):
        """Accessing the public report page increments view_count."""
        org = _make_org("VcOrg")
        coach = _make_user("vc_coach")
        athlete = _make_user("vc_athlete")
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)
        report = _make_report(org, athlete, coach, athlete_m)
        assert report.view_count == 0

        client = APIClient()
        client.get(f"/report/{report.token}/")
        client.get(f"/report/{report.token}/")

        report.refresh_from_db()
        assert report.view_count == 2
        assert report.viewed_at is not None


@pytest.mark.django_db
class TestEmailReport:
    def test_email_endpoint_rejects_invalid_email(self):
        """POST with invalid email returns 400."""
        org = _make_org("EmailOrg")
        coach = _make_user("email_coach")
        athlete = _make_user("email_athlete")
        _make_membership(coach, org, Membership.Role.OWNER)
        athlete_m = _make_membership(athlete, org, Membership.Role.ATHLETE)
        report = _make_report(org, athlete, coach, athlete_m)

        client = APIClient()
        client.force_authenticate(user=coach)

        res = client.post(
            f"/api/coach/athletes/{athlete_m.pk}/report/{report.token}/email/",
            {"recipient_email": "notanemail"},
            format="json",
        )
        assert res.status_code == 400
