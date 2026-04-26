"""
core/tests_pr188d_cache_invalidation.py

PR-188d Fix 8 — Bug #69: CalendarTimeline cache invalidation on assignment update.

Verifies that after a coach updates a WorkoutAssignment, the cache key
`cal_tl:{org_id}:{athlete_id}:{month_start}:{month_end}` is deleted.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()


@pytest.mark.django_db
class TestCacheInvalidationOnAssignmentUpdate:

    def _setup(self):
        """Create minimal org/coach/athlete/assignment for testing."""
        from core.models import (
            Athlete,
            Coach,
            Membership,
            Organization,
            PlannedWorkout,
            WorkoutAssignment,
            WorkoutLibrary,
        )

        coach_user = User.objects.create_user(username="ci_coach_188d", password="x")
        athlete_user = User.objects.create_user(username="ci_athlete_188d", password="x")
        org = Organization.objects.create(name="CIOrg188d", slug="ci-org-188d")
        Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)
        Membership.objects.create(user=athlete_user, organization=org, role="athlete", is_active=True)
        Coach.objects.create(user=coach_user, organization=org)
        athlete = Athlete.objects.create(user=athlete_user, organization=org)
        library = WorkoutLibrary.objects.create(organization=org, name="CILib")
        pw = PlannedWorkout.objects.create(
            organization=org,
            library=library,
            name="CI Test Workout",
            discipline="run",
            session_type="base",
            estimated_duration_seconds=3600,
        )
        assignment = WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=pw,
            scheduled_date=datetime.date(2026, 5, 15),
            day_order=1,
        )
        return org, athlete, assignment

    def _cache_key(self, org_id, athlete_id, scheduled_date):
        month_start = scheduled_date.replace(day=1)
        if scheduled_date.month == 12:
            month_end = scheduled_date.replace(day=31)
        else:
            month_end = (scheduled_date.replace(month=scheduled_date.month + 1, day=1)
                         - datetime.timedelta(days=1))
        return f"cal_tl:{org_id}:{athlete_id}:{month_start}:{month_end}"

    def test_cache_key_deleted_after_update(self, rf):
        """After perform_update, the current-month cache key must be absent."""
        from core.serializers_p1 import WorkoutAssignmentSerializer
        from core.views_p1 import WorkoutAssignmentViewSet
        from core.models import Membership

        org, athlete, assignment = self._setup()
        key = self._cache_key(org.id, athlete.id, assignment.scheduled_date)

        # Pre-seed the cache so we can verify it gets deleted
        cache.set(key, {"plans": [], "activities": [], "reconciliations": []}, timeout=300)
        assert cache.get(key) is not None, "Pre-condition: cache key must exist before update"

        # Simulate a PATCH request via ViewSet
        coach_user = User.objects.get(username="ci_coach_188d")
        request = rf.patch(
            f"/api/p1/orgs/{org.id}/assignments/{assignment.id}/",
            {"athlete_notes": "Test note"},
            content_type="application/json",
        )
        request.user = coach_user

        membership = Membership.objects.get(user=coach_user, organization=org)

        view = WorkoutAssignmentViewSet()
        view.request = request
        view.kwargs = {"org_id": str(org.id), "pk": str(assignment.id)}
        view.organization = org
        view.membership = membership

        serializer = WorkoutAssignmentSerializer(
            assignment,
            data={"athlete_notes": "Test note"},
            partial=True,
            context={"request": request, "organization": org},
        )
        serializer.is_valid(raise_exception=True)
        view.perform_update(serializer)

        assert cache.get(key) is None, "Cache key must be deleted after perform_update"
