"""
core/tests_athlete_profile.py

Tests for AthleteProfile domain model (PR-105).

AthleteGoal is NOT implemented in this PR.
Blocked by: RaceEvent model (PR-106) not yet available.
AthleteGoal requires a clean organization-first FK target (RaceEvent, not the
legacy Carrera model which has no organization FK).

See docs/ai/tasks/PR-106-race-event-model.md for the dependency.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Athlete, AthleteProfile, Organization

User = get_user_model()


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _profile(athlete, org, **kwargs):
    return AthleteProfile.objects.create(athlete=athlete, organization=org, **kwargs)


class AthleteProfileCreationTests(TestCase):
    def setUp(self):
        self.org = _org("profile-org")
        self.user = _user("p_athlete")
        self.athlete = _athlete(self.user, self.org)

    def test_profile_requires_athlete_and_organization(self):
        profile = _profile(self.athlete, self.org)
        self.assertEqual(profile.athlete, self.athlete)
        self.assertEqual(profile.organization, self.org)

    def test_profile_fields_all_nullable_at_creation(self):
        """Profile can be created with only athlete + org — all physio fields optional."""
        profile = _profile(self.athlete, self.org)
        self.assertIsNone(profile.birth_date)
        self.assertIsNone(profile.age)
        self.assertIsNone(profile.height_cm)
        self.assertIsNone(profile.weight_kg)
        self.assertIsNone(profile.bmi)
        self.assertIsNone(profile.resting_hr_bpm)
        self.assertIsNone(profile.max_hr_bpm)
        self.assertIsNone(profile.vo2max)
        self.assertIsNone(profile.ftp_watts)
        self.assertIsNone(profile.vam)
        self.assertIsNone(profile.lactate_threshold_pace_s_per_km)
        self.assertIsNone(profile.running_economy)
        self.assertIsNone(profile.training_age_years)

    def test_profile_default_injury_state_is_false(self):
        profile = _profile(self.athlete, self.org)
        self.assertFalse(profile.is_injured)
        self.assertEqual(profile.injury_notes, "")

    def test_profile_default_zone_payloads_are_empty_dicts(self):
        profile = _profile(self.athlete, self.org)
        self.assertEqual(profile.hr_zones_json, {})
        self.assertEqual(profile.pace_zones_json, {})
        self.assertEqual(profile.power_zones_json, {})

    def test_profile_default_notes_empty(self):
        profile = _profile(self.athlete, self.org)
        self.assertEqual(profile.notes, "")
        self.assertEqual(profile.dominant_discipline, "")

    def test_profile_str(self):
        profile = _profile(self.athlete, self.org)
        result = str(profile)
        self.assertIn("Profile:", result)
        self.assertIn("Athlete:", result)

    def test_profile_updated_at_set(self):
        profile = _profile(self.athlete, self.org)
        self.assertIsNotNone(profile.updated_at)


class AthleteProfileConstraintTests(TestCase):
    def setUp(self):
        self.org = _org("constraint-org")
        self.user = _user("c_athlete")
        self.athlete = _athlete(self.user, self.org)

    def test_one_profile_per_athlete(self):
        """One profile per athlete — enforced at model level via full_clean()."""
        _profile(self.athlete, self.org)
        with self.assertRaises(ValidationError):
            _profile(self.athlete, self.org)

    def test_different_athletes_can_each_have_a_profile(self):
        user2 = _user("c_athlete2")
        athlete2 = _athlete(user2, self.org)
        p1 = _profile(self.athlete, self.org)
        p2 = _profile(athlete2, self.org)
        self.assertEqual(p1.athlete, self.athlete)
        self.assertEqual(p2.athlete, athlete2)

    def test_profile_cascade_deletes_with_athlete(self):
        _profile(self.athlete, self.org)
        self.assertEqual(AthleteProfile.objects.count(), 1)
        self.athlete.delete()
        self.assertEqual(AthleteProfile.objects.count(), 0)

    def test_profile_cascade_deletes_with_organization(self):
        _profile(self.athlete, self.org)
        self.org.delete()
        self.assertEqual(AthleteProfile.objects.count(), 0)


class AthleteProfilePhysioTests(TestCase):
    def setUp(self):
        self.org = _org("physio-org")
        self.athlete = _athlete(_user("physio_a"), self.org)

    def test_profile_stores_all_physio_fields(self):
        profile = _profile(
            self.athlete, self.org,
            weight_kg=72.5,
            height_cm=178.0,
            age=32,
            bmi=22.9,
            resting_hr_bpm=48,
            max_hr_bpm=192,
            vo2max=58.3,
            ftp_watts=310,
            vam=1200.0,
            lactate_threshold_pace_s_per_km=240,
            running_economy=195.0,
            training_age_years=8,
        )
        self.assertEqual(profile.weight_kg, 72.5)
        self.assertEqual(profile.height_cm, 178.0)
        self.assertEqual(profile.age, 32)
        self.assertAlmostEqual(profile.bmi, 22.9)
        self.assertEqual(profile.resting_hr_bpm, 48)
        self.assertEqual(profile.max_hr_bpm, 192)
        self.assertAlmostEqual(profile.vo2max, 58.3)
        self.assertEqual(profile.ftp_watts, 310)
        self.assertAlmostEqual(profile.vam, 1200.0)
        self.assertEqual(profile.lactate_threshold_pace_s_per_km, 240)
        self.assertAlmostEqual(profile.running_economy, 195.0)
        self.assertEqual(profile.training_age_years, 8)

    def test_profile_injury_can_be_set(self):
        profile = _profile(
            self.athlete, self.org,
            is_injured=True,
            injury_notes="Left knee tendinopathy",
        )
        self.assertTrue(profile.is_injured)
        self.assertEqual(profile.injury_notes, "Left knee tendinopathy")

    def test_profile_zones_stored_as_json(self):
        hr_zones = {"z1": {"min_bpm": 0, "max_bpm": 120}, "z2": {"min_bpm": 121, "max_bpm": 140}}
        pace_zones = {"z1": {"min_s_km": 360, "max_s_km": 420}}
        power_zones = {"z1": {"min_w": 0, "max_w": 150}, "z7": {"min_w": 450, "max_w": 999}}
        profile = _profile(
            self.athlete, self.org,
            hr_zones_json=hr_zones,
            pace_zones_json=pace_zones,
            power_zones_json=power_zones,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.hr_zones_json["z1"]["min_bpm"], 0)
        self.assertEqual(profile.pace_zones_json["z1"]["min_s_km"], 360)
        self.assertEqual(profile.power_zones_json["z7"]["min_w"], 450)

    def test_profile_dominant_discipline_choices(self):
        from .models import AthleteProfile
        valid = [c[0] for c in AthleteProfile.Discipline.choices]
        self.assertIn("run", valid)
        self.assertIn("trail", valid)
        self.assertIn("bike", valid)
        self.assertIn("swim", valid)
        self.assertIn("triathlon", valid)
        self.assertIn("other", valid)

    def test_profile_organization_must_match_athlete_organization(self):
        """
        Fail-closed: profile.organization must equal athlete.organization.
        Valid case: same org passes without error.
        """
        profile = _profile(self.athlete, self.org)
        self.assertEqual(profile.organization, self.athlete.organization)

    def test_profile_cross_org_raises_validation_error(self):
        """
        Fail-closed: creating a profile whose organization differs from the
        athlete's organization must be rejected at the model level.
        This is Quantoryn Law #1 — tenant consistency is not optional.
        """
        other_org = _org("other-org-profile")
        with self.assertRaises(ValidationError):
            AthleteProfile.objects.create(
                athlete=self.athlete,
                organization=other_org,
            )
