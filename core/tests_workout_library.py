"""
core/tests_workout_library.py

Tests for WorkoutLibrary domain model (PR-111).

WorkoutLibrary is an organization-scoped named container for workout templates.
PlannedWorkout records with is_template=True will reference this library (PR-112).

Covers:
- Creation with required fields
- Default values (is_public, description)
- Name unique per organization (unique_together)
- Same name allowed across different organizations
- Cascade delete with organization
- created_by SET_NULL on user delete
- Visibility flag (is_public)
- __str__ representation
- Ordering by name
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .models import Organization, WorkoutLibrary

User = get_user_model()


def _org(slug):
    return Organization.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _library(org, name="Base Endurance", **kwargs):
    return WorkoutLibrary.objects.create(organization=org, name=name, **kwargs)


class WorkoutLibraryCreationTests(TestCase):
    def setUp(self):
        self.org = _org("lib-org")

    def test_library_requires_organization_and_name(self):
        lib = _library(self.org)
        self.assertEqual(lib.organization, self.org)
        self.assertEqual(lib.name, "Base Endurance")

    def test_is_public_defaults_to_true(self):
        lib = _library(self.org)
        self.assertTrue(lib.is_public)

    def test_description_defaults_to_empty(self):
        lib = _library(self.org)
        self.assertEqual(lib.description, "")

    def test_created_by_defaults_to_none(self):
        lib = _library(self.org)
        self.assertIsNone(lib.created_by)

    def test_optional_fields_can_be_set(self):
        user = _user("coach_a")
        lib = _library(
            self.org,
            name="Trail Intervals",
            description="High-intensity trail-specific intervals.",
            is_public=False,
            created_by=user,
        )
        self.assertEqual(lib.description, "High-intensity trail-specific intervals.")
        self.assertFalse(lib.is_public)
        self.assertEqual(lib.created_by, user)

    def test_timestamps_set_on_creation(self):
        lib = _library(self.org)
        self.assertIsNotNone(lib.created_at)
        self.assertIsNotNone(lib.updated_at)


class WorkoutLibraryStrTests(TestCase):
    def setUp(self):
        self.org = _org("str-org")

    def test_str_public_library(self):
        lib = _library(self.org, name="Speed Work", is_public=True)
        result = str(lib)
        self.assertIn("Speed Work", result)
        self.assertIn("public", result)

    def test_str_private_library(self):
        lib = _library(self.org, name="Private Sessions", is_public=False)
        result = str(lib)
        self.assertIn("Private Sessions", result)
        self.assertIn("private", result)


class WorkoutLibraryUniquenessTests(TestCase):
    def setUp(self):
        self.org_a = _org("uniq-org-a")
        self.org_b = _org("uniq-org-b")

    def test_name_unique_per_organization(self):
        _library(self.org_a, name="Threshold Block")
        with self.assertRaises(IntegrityError):
            _library(self.org_a, name="Threshold Block")

    def test_same_name_allowed_across_different_organizations(self):
        lib_a = _library(self.org_a, name="Threshold Block")
        lib_b = _library(self.org_b, name="Threshold Block")
        self.assertEqual(lib_a.name, lib_b.name)
        self.assertNotEqual(lib_a.organization, lib_b.organization)

    def test_different_names_within_same_org_are_allowed(self):
        _library(self.org_a, name="Library One")
        _library(self.org_a, name="Library Two")
        self.assertEqual(WorkoutLibrary.objects.filter(organization=self.org_a).count(), 2)


class WorkoutLibraryVisibilityTests(TestCase):
    def setUp(self):
        self.org = _org("vis-org")

    def test_public_library_created_with_is_public_true(self):
        lib = _library(self.org, is_public=True)
        self.assertTrue(lib.is_public)
        lib.refresh_from_db()
        self.assertTrue(lib.is_public)

    def test_private_library_created_with_is_public_false(self):
        lib = _library(self.org, is_public=False)
        self.assertFalse(lib.is_public)
        lib.refresh_from_db()
        self.assertFalse(lib.is_public)

    def test_visibility_can_be_toggled(self):
        lib = _library(self.org, is_public=True)
        lib.is_public = False
        lib.save()
        lib.refresh_from_db()
        self.assertFalse(lib.is_public)


class WorkoutLibraryCascadeTests(TestCase):
    def setUp(self):
        self.org = _org("cascade-lib-org")

    def test_cascade_delete_with_organization(self):
        _library(self.org, name="Will Be Deleted")
        self.assertEqual(WorkoutLibrary.objects.count(), 1)
        self.org.delete()
        self.assertEqual(WorkoutLibrary.objects.count(), 0)

    def test_created_by_set_null_on_user_delete(self):
        user = _user("coach_to_delete")
        lib = _library(self.org, created_by=user)
        self.assertEqual(lib.created_by, user)
        user.delete()
        lib.refresh_from_db()
        self.assertIsNone(lib.created_by)

    def test_multiple_libraries_cascade_delete_together(self):
        _library(self.org, name="Library Alpha")
        _library(self.org, name="Library Beta")
        self.assertEqual(WorkoutLibrary.objects.filter(organization=self.org).count(), 2)
        self.org.delete()
        self.assertEqual(WorkoutLibrary.objects.count(), 0)


class WorkoutLibraryOrderingTests(TestCase):
    def setUp(self):
        self.org = _org("order-lib-org")

    def test_libraries_ordered_by_name_ascending(self):
        _library(self.org, name="Zebra Workouts")
        _library(self.org, name="Alpha Base")
        _library(self.org, name="Marathon Prep")
        libs = list(WorkoutLibrary.objects.filter(organization=self.org))
        names = [l.name for l in libs]
        self.assertEqual(names, sorted(names))
