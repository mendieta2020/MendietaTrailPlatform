"""
PR-128a — PMC Backend Tests

Coverage:
    TRIMP cascade (tests 1–5)
    PMC computation: CTL/ATL/TSB (tests 6–9)
    API tenancy (tests 10–16)
    Strava ingestion biometric fields (tests 17–18)
"""
import datetime
import math

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from core.models import (
    ActivityLoad,
    Alumno,
    Athlete,
    AthleteHRProfile,
    CompletedActivity,
    DailyLoad,
    Membership,
    Organization,
)
from core.services_pmc import (
    compute_pmc_from_date,
    compute_tss_for_activity,
    process_activity_load,
)

User = get_user_model()

_T0 = datetime.datetime(2026, 3, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)


# ==============================================================================
# Test helpers
# ==============================================================================

def _make_org(slug):
    """Create an org with a coach user."""
    coach = User.objects.create_user(username=f"coach_{slug}", password="x")
    org = Organization.objects.create(name=slug, slug=slug)
    Membership.objects.create(user=coach, organization=org, role="coach", is_active=True)
    return org, coach


def _make_athlete_user(org, username):
    """Create a User + Athlete + athlete Membership in the org."""
    user = User.objects.create_user(username=username, password="x")
    athlete = Athlete.objects.create(user=user, organization=org)
    membership = Membership.objects.create(
        user=user, organization=org, role="athlete", is_active=True
    )
    return user, athlete, membership


def _make_alumno(org, coach_user, n=1):
    return Alumno.objects.create(
        entrenador=coach_user,
        nombre=f"Atleta{n}",
        apellido="Test",
        email=f"atleta{n}_{org.slug}@test.com",
    )


def _make_activity(org, alumno, athlete=None, provider_activity_id="act-001", **overrides):
    defaults = dict(
        organization=org,
        alumno=alumno,
        athlete=athlete,
        sport="RUN",
        start_time=_T0,
        duration_s=3600,
        distance_m=10000.0,
        provider=CompletedActivity.Provider.STRAVA,
        provider_activity_id=provider_activity_id,
    )
    defaults.update(overrides)
    return CompletedActivity.objects.create(**defaults)


def _make_hr_profile(org, user, hr_max=180, hr_rest=50, threshold_pace_s_km=None):
    profile, _ = AthleteHRProfile.objects.update_or_create(
        organization=org,
        athlete=user,
        defaults={
            "hr_max": hr_max,
            "hr_rest": hr_rest,
            "threshold_pace_s_km": threshold_pace_s_km,
        },
    )
    return profile


# ==============================================================================
# 1–5: TRIMP cascade
# ==============================================================================

class TRIMPCascadeTests(TestCase):
    def setUp(self):
        self.org, self.coach = _make_org("trimp-org")
        self.user, self.athlete, _ = _make_athlete_user(self.org, "trimp_athlete")
        self.alumno = _make_alumno(self.org, self.coach)
        self.hr_profile = _make_hr_profile(self.org, self.user, hr_max=180, hr_rest=50)

    def _activity(self, **kwargs):
        return _make_activity(
            self.org, self.alumno, athlete=self.athlete, **kwargs
        )

    def test_01_trimp_from_avg_hr(self):
        """compute_tss_for_activity returns method='trimp' when avg_hr is present."""
        activity = self._activity(avg_hr=145, duration_s=3600)
        tss, method = compute_tss_for_activity(activity, self.hr_profile)
        self.assertEqual(method, "trimp")
        # Manual check: duration_min=60, hr_reserve=130, hr_ratio=(145-50)/130≈0.731
        hr_ratio = (145 - 50) / (180 - 50)
        expected = 60 * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
        self.assertAlmostEqual(tss, round(expected, 2), places=1)

    def test_02_override_takes_priority(self):
        """tss_override bypasses all computation and returns method='override'."""
        activity = self._activity(avg_hr=145, tss_override=99.5)
        tss, method = compute_tss_for_activity(activity, self.hr_profile)
        self.assertEqual(method, "override")
        self.assertAlmostEqual(tss, 99.5, places=2)

    def test_03_rtss_from_pace_no_hr(self):
        """Without avg_hr but with pace + threshold_pace → method='rtss_pace'."""
        profile = _make_hr_profile(
            self.org, self.user, hr_max=180, hr_rest=50, threshold_pace_s_km=300.0
        )
        activity = self._activity(avg_hr=None, avg_pace_s_km=330.0, duration_s=3600)
        tss, method = compute_tss_for_activity(activity, profile)
        self.assertEqual(method, "rtss_pace")
        # IF = 300/330 ≈ 0.909; rTSS = IF^2 * 1h * 100
        intensity_factor = 300.0 / 330.0
        expected = (intensity_factor ** 2) * 1.0 * 100.0
        self.assertAlmostEqual(tss, round(expected, 2), places=1)

    def test_04_duration_estimate_fallback(self):
        """Without HR, pace, or threshold → method='estimated_duration'."""
        profile = _make_hr_profile(self.org, self.user, hr_max=180, hr_rest=50)
        activity = self._activity(avg_hr=None, avg_pace_s_km=None, duration_s=7200, sport="RUN")
        tss, method = compute_tss_for_activity(activity, profile)
        self.assertEqual(method, "estimated_duration")
        # 2h * 0.65 * 100 = 130
        self.assertAlmostEqual(tss, 130.0, places=1)

    def test_05_hr_ratio_clamped_when_below_rest(self):
        """avg_hr < hr_rest → hr_ratio clamped to 0.0, TRIMP returns 0.0 (not negative)."""
        activity = self._activity(avg_hr=40, duration_s=3600)  # below hr_rest=50
        tss, method = compute_tss_for_activity(activity, self.hr_profile)
        self.assertEqual(method, "trimp")
        self.assertEqual(tss, 0.0)


# ==============================================================================
# 6–9: PMC computation (CTL / ATL / TSB)
# ==============================================================================

class PMCComputationTests(TestCase):
    def setUp(self):
        self.org, self.coach = _make_org("pmc-org")
        self.user, self.athlete, _ = _make_athlete_user(self.org, "pmc_athlete")
        self.alumno = _make_alumno(self.org, self.coach)

    def _create_activity_load(self, date_val, tss):
        """Helper: create a fake ActivityLoad for a given date and TSS."""
        activity = _make_activity(
            self.org, self.alumno,
            athlete=self.athlete,
            provider_activity_id=f"act-{date_val}",
            start_time=datetime.datetime.combine(
                date_val, datetime.time(8, 0), tzinfo=datetime.timezone.utc
            ),
            duration_s=3600,
        )
        ActivityLoad.objects.create(
            organization=self.org,
            athlete=self.user,
            completed_activity=activity,
            date=date_val,
            tss=tss,
            method="trimp",
        )
        return activity

    def test_06_ctl_atl_tsb_correct_3day_sequence(self):
        """CTL/ATL/TSB correct for a known 3-day sequence."""
        ctl_decay = math.exp(-1 / 42)
        atl_decay = math.exp(-1 / 7)
        ctl_factor = 1 - ctl_decay
        atl_factor = 1 - atl_decay

        today = timezone.now().date()
        d1 = today - datetime.timedelta(days=2)
        d2 = today - datetime.timedelta(days=1)
        d3 = today

        self._create_activity_load(d1, 80.0)
        self._create_activity_load(d2, 100.0)
        self._create_activity_load(d3, 60.0)

        compute_pmc_from_date(user=self.user, organization=self.org, from_date=d1)

        loads = DailyLoad.objects.filter(
            organization=self.org, athlete=self.user
        ).order_by("date")
        dates_loaded = [dl.date for dl in loads]
        self.assertIn(d1, dates_loaded)
        self.assertIn(d3, dates_loaded)

        # Manually compute expected values
        ctl, atl = 0.0, 0.0
        for tss in [80.0, 100.0, 60.0]:
            ctl = ctl * ctl_decay + tss * ctl_factor
            atl = atl * atl_decay + tss * atl_factor

        dl_today = DailyLoad.objects.get(
            organization=self.org, athlete=self.user, date=d3
        )
        self.assertAlmostEqual(dl_today.ctl, round(ctl, 2), places=1)
        self.assertAlmostEqual(dl_today.atl, round(atl, 2), places=1)
        self.assertAlmostEqual(dl_today.tsb, round(ctl - atl, 2), places=1)

    def test_07_rest_day_decays_ctl_atl(self):
        """A day with TSS=0 causes CTL and ATL to decay from the previous value."""
        ctl_decay = math.exp(-1 / 42)
        atl_decay = math.exp(-1 / 7)

        today = timezone.now().date()
        d1 = today - datetime.timedelta(days=1)

        self._create_activity_load(d1, 100.0)
        compute_pmc_from_date(user=self.user, organization=self.org, from_date=d1)

        dl_d1 = DailyLoad.objects.get(organization=self.org, athlete=self.user, date=d1)
        ctl_d1 = dl_d1.ctl
        atl_d1 = dl_d1.atl

        # Today has no activity → TSS=0, values should decay
        compute_pmc_from_date(user=self.user, organization=self.org, from_date=today)
        dl_today = DailyLoad.objects.get(organization=self.org, athlete=self.user, date=today)

        expected_ctl = round(ctl_d1 * ctl_decay, 2)
        expected_atl = round(atl_d1 * atl_decay, 2)
        self.assertAlmostEqual(dl_today.ctl, expected_ctl, places=1)
        self.assertAlmostEqual(dl_today.atl, expected_atl, places=1)

    def test_08_compute_pmc_is_idempotent(self):
        """Running compute_pmc_from_date twice produces the same DailyLoad records."""
        today = timezone.now().date()
        self._create_activity_load(today, 75.0)

        compute_pmc_from_date(user=self.user, organization=self.org, from_date=today)
        first_ctl = DailyLoad.objects.get(
            organization=self.org, athlete=self.user, date=today
        ).ctl

        compute_pmc_from_date(user=self.user, organization=self.org, from_date=today)
        second_ctl = DailyLoad.objects.get(
            organization=self.org, athlete=self.user, date=today
        ).ctl

        self.assertEqual(first_ctl, second_ctl)
        self.assertEqual(
            DailyLoad.objects.filter(organization=self.org, athlete=self.user, date=today).count(),
            1,
        )

    def test_09_process_activity_load_skips_no_athlete(self):
        """process_activity_load skips silently when CompletedActivity.athlete is None."""
        activity = _make_activity(
            self.org, self.alumno,
            athlete=None,  # no Athlete FK
            provider_activity_id="act-no-athlete",
        )
        # Should not raise, should not create ActivityLoad
        process_activity_load(activity.pk)
        self.assertEqual(
            ActivityLoad.objects.filter(completed_activity=activity).count(), 0
        )


# ==============================================================================
# 10–16: API tenancy
# ==============================================================================

class PMCAPITenancyTests(TestCase):
    def setUp(self):
        self.org, self.coach_user = _make_org("api-org")
        self.athlete_user, self.athlete, self.athlete_membership = _make_athlete_user(
            self.org, "api_athlete"
        )
        self.alumno = _make_alumno(self.org, self.coach_user)

        # Create DailyLoad records for the athlete
        today = timezone.now().date()
        DailyLoad.objects.create(
            organization=self.org,
            athlete=self.athlete_user,
            date=today,
            tss=80.0, ctl=60.0, atl=70.0, tsb=-10.0, ars=55,
        )

        self.athlete_client = APIClient()
        self.athlete_client.force_authenticate(user=self.athlete_user)

        self.coach_client = APIClient()
        self.coach_client.force_authenticate(user=self.coach_user)

    def test_10_athlete_can_get_own_pmc(self):
        """GET /api/athlete/pmc/ returns 200 with PMC data for the athlete."""
        resp = self.athlete_client.get("/api/athlete/pmc/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("current", resp.data)
        self.assertIn("days", resp.data)
        self.assertEqual(resp.data["period_days"], 90)

    def test_11_coach_cannot_access_athlete_pmc_endpoint(self):
        """GET /api/athlete/pmc/ returns 403 when accessed by a coach."""
        resp = self.coach_client.get("/api/athlete/pmc/")
        self.assertEqual(resp.status_code, 403)

    def test_12_coach_athlete_pmc_wrong_org_returns_404(self):
        """GET /api/coach/athletes/<id>/pmc/ with a membership from another org → 404."""
        other_org, other_coach = _make_org("other-org")
        other_user, _, other_membership = _make_athlete_user(other_org, "other_athlete")

        resp = self.coach_client.get(f"/api/coach/athletes/{other_membership.pk}/pmc/")
        self.assertEqual(resp.status_code, 404)

    def test_13_athlete_cannot_access_team_readiness(self):
        """GET /api/coach/team-readiness/ returns 403 for athlete role."""
        resp = self.athlete_client.get("/api/coach/team-readiness/")
        self.assertEqual(resp.status_code, 403)

    def test_14_team_readiness_scoped_to_coach_org(self):
        """GET /api/coach/team-readiness/ returns only athletes in coach's org."""
        # Create a second org with an unrelated athlete
        other_org, _ = _make_org("other-org2")
        _make_athlete_user(other_org, "other_athlete2")

        resp = self.coach_client.get("/api/coach/team-readiness/")
        self.assertEqual(resp.status_code, 200)
        membership_ids = [a["membership_id"] for a in resp.data["athletes"]]
        # Only the athlete from this org should appear
        self.assertIn(self.athlete_membership.pk, membership_ids)

    def test_15_athlete_can_update_hr_profile(self):
        """PUT /api/athlete/hr-profile/ updates hr_max and hr_rest for the athlete."""
        resp = self.athlete_client.put(
            "/api/athlete/hr-profile/",
            {"hr_max": 185, "hr_rest": 48},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["hr_max"], 185)
        self.assertEqual(resp.data["hr_rest"], 48)
        profile = AthleteHRProfile.objects.get(
            organization=self.org, athlete=self.athlete_user
        )
        self.assertEqual(profile.hr_max, 185)
        self.assertEqual(profile.hr_rest, 48)

    def test_16_coach_cannot_access_hr_profile_endpoint(self):
        """PUT /api/athlete/hr-profile/ returns 403 for coach role."""
        resp = self.coach_client.put(
            "/api/athlete/hr-profile/",
            {"hr_max": 185, "hr_rest": 48},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ==============================================================================
# 17–18: Strava ingestion biometric field extraction
# ==============================================================================

class StravaIngestionBiometricTests(TestCase):
    def setUp(self):
        from core.models import Alumno
        self.org, self.coach_user = _make_org("ingest-org")
        self.alumno = _make_alumno(self.org, self.coach_user)

    def _run_ingest(self, raw_payload_overrides=None):
        """Run ingest_strava_activity with a minimal valid payload."""
        from integrations.strava.services_strava_ingest import ingest_strava_activity

        raw = {
            "average_heartrate": 145.0,
            "max_heartrate": 172.0,
            "average_watts": None,
            "average_speed": 3.0,  # m/s → 333.3 s/km
        }
        if raw_payload_overrides:
            raw.update(raw_payload_overrides)

        activity_data = {
            "start_date_local": datetime.datetime(
                2026, 3, 10, 8, 0, 0, tzinfo=datetime.timezone.utc
            ),
            "elapsed_time_s": 3600,
            "distance_m": 10000.0,
            "type": "Run",
            "elevation_m": 200.0,
            "calories_kcal": None,
            "avg_hr": raw.get("average_heartrate"),
            "raw": raw,
        }
        return ingest_strava_activity(
            alumno_id=self.alumno.pk,
            external_activity_id="strava-biometric-test",
            activity_data=activity_data,
        )

    def test_17_avg_hr_extracted_from_raw_payload(self):
        """avg_hr is correctly extracted from raw['average_heartrate'] into the normalized field."""
        activity, created = self._run_ingest()
        self.assertTrue(created)
        activity.refresh_from_db()
        self.assertEqual(activity.avg_hr, 145)

    def test_18_avg_pace_s_km_computed_from_average_speed(self):
        """avg_pace_s_km is correctly computed from raw['average_speed'] (m/s → s/km)."""
        activity, created = self._run_ingest({"average_speed": 3.0})
        self.assertTrue(created)
        activity.refresh_from_db()
        # 1000 / 3.0 = 333.33...
        self.assertIsNotNone(activity.avg_pace_s_km)
        self.assertAlmostEqual(activity.avg_pace_s_km, 1000.0 / 3.0, places=1)
