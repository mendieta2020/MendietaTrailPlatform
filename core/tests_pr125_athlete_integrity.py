"""
core/tests_pr125_athlete_integrity.py

PR-125: Athlete Identity Integrity Layer

Tests for the Athlete.clean() cross-field organization validation.
Ensures that coach and team FKs are always scoped to the same organization
as the Athlete at the model layer (defense-in-depth beyond the serializer).

Coverage:
  1. Clean athlete (no coach, no team) → no error
  2. Coach from same org → no error
  3. Team from same org → no error
  4. Coach from different org → ValidationError on 'coach'
  5. Team from different org → ValidationError on 'team'
  6. Both coach and team from different orgs → ValidationError with both fields
  7. Coach from same org, team from different org → ValidationError only on 'team'
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.models import Athlete, Coach, Membership, Organization, Team

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (mirror the pattern from tests_p1_roster.py)
# ---------------------------------------------------------------------------

def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role="athlete"):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _team(org, name="Team A"):
    return Team.objects.create(organization=org, name=name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org_a(db):
    return _org("org-a")


@pytest.fixture
def org_b(db):
    return _org("org-b")


@pytest.fixture
def athlete_user(db):
    return _user("athlete-user")


@pytest.fixture
def coach_user_a(db):
    return _user("coach-user-a")


@pytest.fixture
def coach_user_b(db):
    return _user("coach-user-b")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAthleteClean:

    def test_clean_athlete_no_coach_no_team_passes(self, org_a, athlete_user):
        """Athlete with no coach and no team is always valid."""
        athlete = Athlete(user=athlete_user, organization=org_a)
        athlete.clean()  # must not raise

    def test_clean_coach_same_org_passes(self, org_a, athlete_user, coach_user_a):
        """Coach from the same org is valid."""
        _membership(coach_user_a, org_a, role="coach")
        coach = _coach(coach_user_a, org_a)
        athlete = Athlete(user=athlete_user, organization=org_a, coach=coach)
        athlete.clean()  # must not raise

    def test_clean_team_same_org_passes(self, org_a, athlete_user):
        """Team from the same org is valid."""
        team = _team(org_a)
        athlete = Athlete(user=athlete_user, organization=org_a, team=team)
        athlete.clean()  # must not raise

    def test_clean_coach_different_org_raises(self, org_a, org_b, athlete_user, coach_user_b):
        """Coach from a different org must raise ValidationError on 'coach'."""
        _membership(coach_user_b, org_b, role="coach")
        coach_b = _coach(coach_user_b, org_b)
        athlete = Athlete(user=athlete_user, organization=org_a, coach=coach_b)

        with pytest.raises(ValidationError) as exc_info:
            athlete.clean()

        assert "coach" in exc_info.value.message_dict
        assert "team" not in exc_info.value.message_dict

    def test_clean_team_different_org_raises(self, org_a, org_b, athlete_user):
        """Team from a different org must raise ValidationError on 'team'."""
        team_b = _team(org_b, name="Team B")
        athlete = Athlete(user=athlete_user, organization=org_a, team=team_b)

        with pytest.raises(ValidationError) as exc_info:
            athlete.clean()

        assert "team" in exc_info.value.message_dict
        assert "coach" not in exc_info.value.message_dict

    def test_clean_both_coach_and_team_different_org_raises_both_fields(
        self, org_a, org_b, athlete_user, coach_user_b
    ):
        """When both coach and team are from a different org, both fields are reported."""
        _membership(coach_user_b, org_b, role="coach")
        coach_b = _coach(coach_user_b, org_b)
        team_b = _team(org_b, name="Team B")
        athlete = Athlete(user=athlete_user, organization=org_a, coach=coach_b, team=team_b)

        with pytest.raises(ValidationError) as exc_info:
            athlete.clean()

        assert "coach" in exc_info.value.message_dict
        assert "team" in exc_info.value.message_dict

    def test_clean_coach_same_org_team_different_org_raises_only_team(
        self, org_a, org_b, athlete_user, coach_user_a
    ):
        """Coach same org + team different org → only 'team' field in error."""
        _membership(coach_user_a, org_a, role="coach")
        coach_a = _coach(coach_user_a, org_a)
        team_b = _team(org_b, name="Team B")
        athlete = Athlete(user=athlete_user, organization=org_a, coach=coach_a, team=team_b)

        with pytest.raises(ValidationError) as exc_info:
            athlete.clean()

        assert "team" in exc_info.value.message_dict
        assert "coach" not in exc_info.value.message_dict
