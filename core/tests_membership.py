"""
core/tests_membership.py

Tests for the Membership model and fail-closed tenancy gate (PR-102).

Covers:
- Membership model constraints and state transitions
- get_active_membership() fail-closed behavior
- require_role() fail-closed behavior
- OrgTenantMixin resolution

No existing model, view, or tenancy function is modified by this PR.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.test import TestCase

from .models import Membership, Organization, Team
from .tenancy import get_active_membership, require_role, OrgTenantMixin

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_org(slug):
    return Organization.objects.create(name=slug.title(), slug=slug)


class MembershipModelTests(TestCase):
    def setUp(self):
        self.user = _make_user("athlete1")
        self.org = _make_org("test-org")

    def test_membership_created_with_required_fields(self):
        m = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.ATHLETE,
        )
        self.assertEqual(m.user, self.user)
        self.assertEqual(m.organization, self.org)
        self.assertEqual(m.role, Membership.Role.ATHLETE)
        self.assertTrue(m.is_active)
        self.assertIsNotNone(m.joined_at)
        self.assertIsNone(m.left_at)

    def test_active_membership_unique_per_user_org(self):
        Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.ATHLETE
        )
        with self.assertRaises(IntegrityError):
            Membership.objects.create(
                user=self.user, organization=self.org, role=Membership.Role.COACH
            )

    def test_two_inactive_memberships_allowed(self):
        # Historical memberships (is_active=False) are not constrained
        Membership.objects.create(
            user=self.user, organization=self.org,
            role=Membership.Role.ATHLETE, is_active=False,
        )
        # Second inactive membership for same user+org must not raise
        m2 = Membership.objects.create(
            user=self.user, organization=self.org,
            role=Membership.Role.COACH, is_active=False,
        )
        self.assertFalse(m2.is_active)

    def test_active_and_inactive_coexist(self):
        # One inactive historical record + one active record = allowed
        Membership.objects.create(
            user=self.user, organization=self.org,
            role=Membership.Role.ATHLETE, is_active=False,
        )
        m_active = Membership.objects.create(
            user=self.user, organization=self.org,
            role=Membership.Role.COACH, is_active=True,
        )
        self.assertTrue(m_active.is_active)

    def test_membership_str_includes_role(self):
        m = Membership(user=self.user, organization=self.org, role=Membership.Role.COACH)
        result = str(m)
        self.assertIn("coach", result)

    def test_membership_all_roles_valid(self):
        roles = [
            Membership.Role.OWNER,
            Membership.Role.COACH,
            Membership.Role.ATHLETE,
            Membership.Role.STAFF,
        ]
        for role in roles:
            self.assertIn(role, Membership.Role.values)

    def test_membership_staff_title_optional(self):
        m = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.STAFF
        )
        self.assertEqual(m.staff_title, "")

    def test_membership_team_nullable(self):
        team = Team.objects.create(organization=self.org, name="Elite")
        m1 = Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.Role.ATHLETE
        )
        self.assertIsNone(m1.team)

        user2 = _make_user("athlete2")
        m2 = Membership.objects.create(
            user=user2, organization=self.org,
            role=Membership.Role.ATHLETE, team=team,
        )
        self.assertEqual(m2.team, team)


class TenancyResolverTests(TestCase):
    def setUp(self):
        self.user = _make_user("coach1")
        self.org = _make_org("resolver-org")
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.COACH,
        )

    def test_get_active_membership_returns_membership(self):
        result = get_active_membership(self.user, self.org.id)
        self.assertEqual(result, self.membership)

    def test_get_active_membership_raises_if_no_membership(self):
        other_user = _make_user("stranger")
        with self.assertRaises(PermissionDenied):
            get_active_membership(other_user, self.org.id)

    def test_get_active_membership_raises_if_inactive(self):
        self.membership.is_active = False
        self.membership.save()
        with self.assertRaises(PermissionDenied):
            get_active_membership(self.user, self.org.id)

    def test_get_active_membership_raises_for_wrong_org(self):
        other_org = _make_org("other-org")
        with self.assertRaises(PermissionDenied):
            get_active_membership(self.user, other_org.id)

    def test_require_role_passes_for_allowed_role(self):
        result = require_role(self.user, self.org.id, ["owner", "coach"])
        self.assertEqual(result, self.membership)

    def test_require_role_raises_for_wrong_role(self):
        athlete_user = _make_user("athlete1")
        Membership.objects.create(
            user=athlete_user, organization=self.org, role=Membership.Role.ATHLETE
        )
        with self.assertRaises(PermissionDenied):
            require_role(athlete_user, self.org.id, ["owner", "coach"])

    def test_require_role_raises_if_no_membership(self):
        stranger = _make_user("stranger2")
        with self.assertRaises(PermissionDenied):
            require_role(stranger, self.org.id, ["owner", "coach"])

    def test_require_role_exact_role_match(self):
        # owner role required — coach must be denied
        with self.assertRaises(PermissionDenied):
            require_role(self.user, self.org.id, ["owner"])

    def test_require_role_single_role_list(self):
        result = require_role(self.user, self.org.id, ["coach"])
        self.assertEqual(result.role, Membership.Role.COACH)


class OrgTenantMixinTests(TestCase):
    def setUp(self):
        self.user = _make_user("owner1")
        self.org = _make_org("mixin-org")
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.OWNER,
        )

    def test_resolve_membership_sets_membership_and_organization(self):
        class FakeRequest:
            user = self.user

        class FakeView(OrgTenantMixin):
            request = FakeRequest()

        view = FakeView()
        result = view.resolve_membership(self.org.id)
        self.assertEqual(result, self.membership)
        self.assertEqual(view.membership, self.membership)
        self.assertEqual(view.organization, self.org)

    def test_resolve_membership_raises_for_no_membership(self):
        stranger = _make_user("stranger3")

        class FakeRequest:
            user = stranger

        class FakeView(OrgTenantMixin):
            request = FakeRequest()

        view = FakeView()
        with self.assertRaises(PermissionDenied):
            view.resolve_membership(self.org.id)
