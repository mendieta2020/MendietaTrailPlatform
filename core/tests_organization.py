"""
core/tests_organization.py

Tests for the Organization and Team domain foundation models (PR-101).

These models are the tenant root for all Quantoryn domain entities.
No existing model, view, or test is modified by this file.
"""
from django.db import IntegrityError
from django.test import TestCase

from .models import Organization, Team


class OrganizationModelTests(TestCase):
    def test_organization_created_with_required_fields(self):
        org = Organization.objects.create(name="Trail Org", slug="trail-org")
        self.assertEqual(org.name, "Trail Org")
        self.assertEqual(org.slug, "trail-org")
        self.assertTrue(org.is_active)
        self.assertIsNotNone(org.created_at)
        self.assertIsNotNone(org.updated_at)

    def test_organization_slug_is_unique(self):
        Organization.objects.create(name="Org A", slug="org-a")
        with self.assertRaises(IntegrityError):
            Organization.objects.create(name="Org B", slug="org-a")

    def test_organization_str_returns_name(self):
        org = Organization(name="Peak Performance", slug="peak-performance")
        self.assertEqual(str(org), "Peak Performance")

    def test_organization_is_active_defaults_to_true(self):
        org = Organization.objects.create(name="Active Org", slug="active-org")
        self.assertTrue(org.is_active)

    def test_organization_can_be_deactivated(self):
        org = Organization.objects.create(name="Old Org", slug="old-org")
        org.is_active = False
        org.save()
        org.refresh_from_db()
        self.assertFalse(org.is_active)


class TeamModelTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", slug="test-org")

    def test_team_requires_organization(self):
        team = Team.objects.create(
            organization=self.org,
            name="Elite Squad",
        )
        self.assertEqual(team.organization, self.org)
        self.assertEqual(team.name, "Elite Squad")

    def test_team_name_unique_per_organization(self):
        Team.objects.create(organization=self.org, name="Team Alpha")
        with self.assertRaises(IntegrityError):
            Team.objects.create(organization=self.org, name="Team Alpha")

    def test_same_team_name_allowed_in_different_orgs(self):
        org2 = Organization.objects.create(name="Other Org", slug="other-org")
        Team.objects.create(organization=self.org, name="Team Alpha")
        # Must not raise — same name is valid in a different org
        team2 = Team.objects.create(organization=org2, name="Team Alpha")
        self.assertEqual(team2.organization, org2)

    def test_team_str_includes_org_name(self):
        team = Team(organization=self.org, name="Trail Elites")
        self.assertIn("Test Org", str(team))
        self.assertIn("Trail Elites", str(team))

    def test_team_cascade_deletes_with_organization(self):
        Team.objects.create(organization=self.org, name="Cascade Team")
        self.assertEqual(Team.objects.filter(organization=self.org).count(), 1)
        self.org.delete()
        self.assertEqual(Team.objects.count(), 0)

    def test_team_is_active_defaults_to_true(self):
        team = Team.objects.create(organization=self.org, name="Active Team")
        self.assertTrue(team.is_active)

    def test_team_description_defaults_to_empty_string(self):
        team = Team.objects.create(organization=self.org, name="Minimal Team")
        self.assertEqual(team.description, "")
