"""
core/views_athlete_card.py — PR-159

Coach-facing read/write endpoints for the Athlete Card (5 tabs).
All endpoints are membership_id-scoped to match the existing PMC pattern.

Endpoints:
    GET  /api/coach/athletes/<membership_id>/profile/    — profile + availability
    PATCH /api/coach/athletes/<membership_id>/profile/   — update profile fields
    GET  /api/coach/athletes/<membership_id>/injuries/   — list injuries
    POST /api/coach/athletes/<membership_id>/injuries/   — create injury
    GET  /api/coach/athletes/<membership_id>/goals/      — list goals
    GET  /api/coach/athletes/<membership_id>/notes/      — get coach notes
    PUT  /api/coach/athletes/<membership_id>/notes/      — update coach notes

Tenancy: org resolved via coach's active Membership. Athlete validated to
         belong to the same org (fail-closed 404).
"""
import logging

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Athlete,
    AthleteAvailability,
    AthleteGoal,
    AthleteInjury,
    AthleteProfile,
    Membership,
    WellnessCheckIn,
)
from core.views_pmc import _get_coach_membership, _resolve_athlete_membership
from core.serializers_p1 import (
    AthleteGoalSerializer,
    AthleteInjurySerializer,
    AthleteProfileSerializer,
    WellnessCheckInSerializer,
)

logger = logging.getLogger(__name__)


def _get_athlete(org, athlete_user):
    """Resolve Athlete from (org, user). 404 if not found."""
    try:
        return Athlete.objects.get(organization=org, user=athlete_user, is_active=True)
    except Athlete.DoesNotExist:
        raise NotFound("Athlete record not found in this organization.")


# ==============================================================================
# Profile — GET / PATCH
# ==============================================================================

class CoachAthleteProfileView(APIView):
    """
    GET  /api/coach/athletes/<membership_id>/profile/
    PATCH /api/coach/athletes/<membership_id>/profile/

    Returns the AthleteProfile + AthleteAvailability for the given athlete.
    Coach (owner/coach role) only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        profile = AthleteProfile.objects.filter(
            organization=org, athlete=athlete
        ).first()

        availability = list(
            AthleteAvailability.objects.filter(
                organization=org, athlete=athlete
            ).order_by("day_of_week").values(
                "id", "day_of_week", "is_available", "reason", "preferred_time"
            )
        )

        profile_data = {}
        if profile:
            serializer = AthleteProfileSerializer(
                profile,
                context={"organization": org},
            )
            profile_data = serializer.data

        payload = {
            "athlete_name": athlete_user.get_full_name() or athlete_user.username,
            "athlete_email": athlete_user.email,
            "athlete_id": athlete.pk,
            "membership_id": membership_id,
            "profile": profile_data,
            "availability": availability,
            "coach_notes": athlete.notes,
        }

        logger.info(
            "coach_athlete_profile.read",
            extra={
                "event_name": "coach_athlete_profile.read",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "outcome": "success",
            },
        )
        return Response(payload)

    def patch(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        profile, _ = AthleteProfile.objects.get_or_create(
            organization=org,
            athlete=athlete,
            defaults={"updated_by": request.user},
        )

        serializer = AthleteProfileSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"organization": org},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)

        logger.info(
            "coach_athlete_profile.updated",
            extra={
                "event_name": "coach_athlete_profile.updated",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "outcome": "success",
            },
        )
        return Response(serializer.data)


# ==============================================================================
# Injuries — GET / POST
# ==============================================================================

class CoachAthleteInjuriesView(APIView):
    """
    GET  /api/coach/athletes/<membership_id>/card-injuries/
    POST /api/coach/athletes/<membership_id>/card-injuries/

    List or create injuries for the given athlete.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        injuries = AthleteInjury.objects.filter(
            organization=org, athlete=athlete
        ).order_by("-date_occurred")

        serializer = AthleteInjurySerializer(injuries, many=True)
        return Response({"results": serializer.data, "count": injuries.count()})

    def post(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        serializer = AthleteInjurySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            organization=org,
            athlete=athlete,
        )

        logger.info(
            "coach_athlete_injury.created",
            extra={
                "event_name": "coach_athlete_injury.created",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "outcome": "success",
            },
        )
        return Response(serializer.data, status=201)


class CoachAthleteInjuryDetailView(APIView):
    """
    PATCH  /api/coach/athletes/<membership_id>/card-injuries/<pk>/
    DELETE /api/coach/athletes/<membership_id>/card-injuries/<pk>/

    PR-161: Update or delete a specific injury for the given athlete.
    """

    permission_classes = [IsAuthenticated]

    def _get_injury(self, org, athlete, pk):
        from rest_framework.exceptions import NotFound
        try:
            return AthleteInjury.objects.get(pk=pk, organization=org, athlete=athlete)
        except AthleteInjury.DoesNotExist:
            raise NotFound("Injury not found.")

    def patch(self, request, membership_id: int, pk: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)
        injury = self._get_injury(org, athlete, pk)

        serializer = AthleteInjurySerializer(injury, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            "coach_athlete_injury.updated",
            extra={
                "event_name": "coach_athlete_injury.updated",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "injury_id": injury.pk,
                "outcome": "success",
            },
        )
        return Response(serializer.data)

    def delete(self, request, membership_id: int, pk: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)
        injury = self._get_injury(org, athlete, pk)

        injury.delete()

        logger.info(
            "coach_athlete_injury.deleted",
            extra={
                "event_name": "coach_athlete_injury.deleted",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "injury_id": pk,
                "outcome": "success",
            },
        )
        return Response(status=204)


# ==============================================================================
# Goals — GET
# ==============================================================================

class CoachAthleteGoalsView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/goals/

    List all goals for the given athlete in the coach's org.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        goals = (
            AthleteGoal.objects
            .filter(organization=org, athlete=athlete)
            .select_related("target_event")
            .order_by("target_date", "priority")
        )

        import datetime
        today = datetime.date.today()
        results = []
        for goal in goals:
            target_date = goal.target_date
            if target_date is None and goal.target_event_id:
                target_date = goal.target_event.event_date if goal.target_event else None
            days_remaining = (target_date - today).days if target_date else None
            results.append({
                "id": goal.pk,
                "title": goal.title,
                "priority": goal.priority,
                "status": goal.status,
                "target_date": target_date.isoformat() if target_date else None,
                "target_distance_km": goal.target_distance_km,
                "target_elevation_gain_m": goal.target_elevation_gain_m,
                "coach_notes": goal.coach_notes,
                "days_remaining": days_remaining,
                "target_event_id": goal.target_event_id,
            })

        return Response({"results": results, "count": len(results)})


# ==============================================================================
# Coach Notes — GET / PUT
# ==============================================================================

class CoachAthleteNotesView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/notes/
    PUT /api/coach/athletes/<membership_id>/notes/

    Read/write the coach's freeform notes about an athlete.
    Stored in Athlete.notes (not athlete-visible in current UI).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)
        return Response({"coach_notes": athlete.notes})

    def put(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(request, membership_id)
        athlete = _get_athlete(org, athlete_user)

        notes = request.data.get("notes", "")
        if not isinstance(notes, str):
            raise ValidationError({"notes": "Must be a string."})

        athlete.notes = notes
        athlete.save(update_fields=["notes", "updated_at"])

        logger.info(
            "coach_athlete_notes.updated",
            extra={
                "event_name": "coach_athlete_notes.updated",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "outcome": "success",
            },
        )
        return Response({"coach_notes": athlete.notes})
