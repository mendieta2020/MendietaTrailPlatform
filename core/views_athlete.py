"""
core/views_athlete.py

Athlete-facing API views. All endpoints are athlete-only (role-gated).

Tenancy: Membership is required; organization is resolved from membership.
Law 6: no PII or secrets in logs.
"""
import logging

from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from core.models import Membership, WorkoutAssignment

logger = logging.getLogger(__name__)


class AthleteTodayView(APIView):
    """
    GET /api/athlete/today/

    Returns the athlete's first active workout scheduled for today.

    Response (workout exists):
        {
            "has_workout": true,
            "workout": {
                "title": "...",
                "description": "...",
                "date": "YYYY-MM-DD"
            }
        }

    Response (no workout today):
        {"has_workout": false}

    403: user has no active membership, or membership role is not "athlete".
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            membership = Membership.objects.select_related("organization").get(
                user=request.user,
                is_active=True,
            )
        except Membership.DoesNotExist:
            return Response(
                {"detail": "No active membership found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if membership.role != Membership.Role.ATHLETE:
            return Response(
                {"detail": "Only athletes can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        org = membership.organization
        today = timezone.localdate()

        assignment = (
            WorkoutAssignment.objects.filter(
                organization=org,
                athlete__user=request.user,
                scheduled_date=today,
                status__in=[
                    WorkoutAssignment.Status.PLANNED,
                    WorkoutAssignment.Status.MOVED,
                ],
            )
            .select_related("planned_workout")
            .order_by("day_order")
            .first()
        )

        has_workout = assignment is not None

        logger.info(
            "athlete_today_fetched",
            extra={
                "event": "athlete_today_fetched",
                "organization_id": org.id,
                "user_id": request.user.id,
                "has_workout": has_workout,
                "outcome": "ok",
            },
        )

        if not has_workout:
            return Response({"has_workout": False})

        pw = assignment.planned_workout
        return Response(
            {
                "has_workout": True,
                "workout": {
                    "title": pw.name,
                    "description": assignment.coach_notes or pw.description,
                    "date": str(assignment.scheduled_date),
                },
            }
        )
