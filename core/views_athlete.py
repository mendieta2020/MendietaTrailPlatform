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
from rest_framework.exceptions import PermissionDenied, NotFound

from core.models import (
    Membership,
    WorkoutAssignment,
    AthleteDevicePreference,
    AthleteNotification,
    OAuthIntegrationStatus,
    Alumno,
)

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


def _resolve_athlete_membership(user):
    """
    Resolve the active Membership with role='athlete' for this user.

    Returns (membership, organization) or raises PermissionDenied.
    Fail-closed: no active athlete membership → 403.
    """
    try:
        membership = Membership.objects.select_related("organization").get(
            user=user,
            is_active=True,
            role=Membership.Role.ATHLETE,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active athlete membership found.")
    return membership, membership.organization


def _athlete_has_device(user):
    """
    Return True if the user has at least one connected provider via OAuthIntegrationStatus.
    Falls back to False if the user has no Alumno record.
    """
    try:
        alumno = Alumno.objects.get(usuario=user)
    except Alumno.DoesNotExist:
        return False
    return OAuthIntegrationStatus.objects.filter(alumno=alumno, connected=True).exists()


class AthleteDeviceStatusView(APIView):
    """
    GET /api/athlete/device-status/

    Returns the current device connection and notification state for the
    authenticated athlete.

    Response:
        {
            "has_device": bool,
            "show_prompt": bool,       # True if no device AND not dismissed
            "dismissed": bool,
            "dismissed_reason": str|null,
            "unread_notifications": int
        }

    403: user is not an active athlete.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        _resolve_athlete_membership(request.user)  # role guard (fail-closed)

        has_device = _athlete_has_device(request.user)

        pref = AthleteDevicePreference.objects.filter(
            athlete=request.user
        ).first()

        dismissed = pref.dismissed if pref else False
        dismissed_reason = pref.dismissed_reason if pref else None

        show_prompt = (not has_device) and (not dismissed)

        # Count unread notifications scoped to this user (any org)
        unread_count = AthleteNotification.objects.filter(
            recipient=request.user,
            read=False,
        ).count()

        return Response({
            "has_device": has_device,
            "show_prompt": show_prompt,
            "dismissed": dismissed,
            "dismissed_reason": dismissed_reason,
            "unread_notifications": unread_count,
        })


class AthleteDevicePreferenceDismissView(APIView):
    """
    POST /api/athlete/device-preference/dismiss/

    Body: {"reason": "no_device"}

    Marks the athlete's device preference as dismissed. Once dismissed, the
    auto-prompt will not re-appear (reversible via reactivate endpoint).

    403: non-athlete calling this endpoint.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        membership, org = _resolve_athlete_membership(request.user)

        reason = request.data.get("reason", "no_device")
        allowed_reasons = [r for r, _ in AthleteDevicePreference.DISMISSED_REASON_CHOICES]
        if reason not in allowed_reasons:
            reason = "no_device"

        pref, _ = AthleteDevicePreference.objects.get_or_create(
            organization=org,
            athlete=request.user,
        )
        pref.dismissed = True
        pref.dismissed_reason = reason
        pref.dismissed_at = timezone.now()
        pref.save(update_fields=["dismissed", "dismissed_reason", "dismissed_at", "updated_at"])

        logger.info(
            "athlete_device_preference_dismissed",
            extra={
                "event": "athlete_device_preference_dismissed",
                "organization_id": org.id,
                "user_id": request.user.id,
                "reason": reason,
                "outcome": "ok",
            },
        )
        return Response({"ok": True})


class AthleteDevicePreferenceReactivateView(APIView):
    """
    POST /api/athlete/device-preference/reactivate/

    Resets the athlete's dismissed preference so the prompt may appear again.
    Called from the athlete's Profile page when they want to reconnect.

    403: non-athlete calling this endpoint.
    404: no preference record found (already not dismissed — noop safe).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        membership, org = _resolve_athlete_membership(request.user)

        try:
            pref = AthleteDevicePreference.objects.get(
                organization=org,
                athlete=request.user,
            )
        except AthleteDevicePreference.DoesNotExist:
            # Already not dismissed — idempotent noop
            return Response({"ok": True})

        pref.dismissed = False
        pref.dismissed_reason = None
        pref.dismissed_at = None
        pref.save(update_fields=["dismissed", "dismissed_reason", "dismissed_at", "updated_at"])

        logger.info(
            "athlete_device_preference_reactivated",
            extra={
                "event": "athlete_device_preference_reactivated",
                "organization_id": org.id,
                "user_id": request.user.id,
                "outcome": "ok",
            },
        )
        return Response({"ok": True})


class AthleteNotificationListView(APIView):
    """
    GET /api/athlete/notifications/

    Returns unread AthleteNotification records for the authenticated athlete,
    ordered by -created_at.

    Response:
        [
            {
                "id": int,
                "notification_type": str,
                "sender_name": str,
                "created_at": str
            },
            ...
        ]

    403: non-athlete.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        _resolve_athlete_membership(request.user)

        notifications = AthleteNotification.objects.filter(
            recipient=request.user,
            read=False,
        ).select_related("sender").order_by("-created_at")

        data = []
        for n in notifications:
            sender_name = "Tu coach"
            if n.sender_id:
                full = n.sender.get_full_name()
                sender_name = full if full.strip() else "Tu coach"
            data.append({
                "id": n.id,
                "notification_type": n.notification_type,
                "sender_name": sender_name,
                "created_at": n.created_at.isoformat(),
            })

        return Response(data)


class AthleteNotificationMarkReadView(APIView):
    """
    POST /api/athlete/notifications/<int:pk>/mark-read/

    Marks a specific notification as read. Fails with 403/404 if the notification
    does not belong to the authenticated athlete in their active organization.

    403: wrong athlete.
    404: notification not found.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        membership, org = _resolve_athlete_membership(request.user)

        try:
            notification = AthleteNotification.objects.get(pk=pk)
        except AthleteNotification.DoesNotExist:
            raise NotFound("Notification not found.")

        # Fail-closed: recipient and org must match
        if notification.recipient_id != request.user.id:
            raise PermissionDenied("Cannot mark another athlete's notification as read.")
        if notification.organization_id != org.id:
            raise PermissionDenied("Notification does not belong to this organization.")

        if not notification.read:
            notification.read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["read", "read_at"])

        return Response({"ok": True})
