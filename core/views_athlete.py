"""
core/views_athlete.py

Athlete-facing API views. All endpoints are athlete-only (role-gated).

Tenancy: Membership is required; organization is resolved from membership.
Law 6: no PII or secrets in logs.
"""
import datetime
import logging

from django.db.models import Sum
from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound

from core.models import (
    Athlete,
    AthleteDevicePreference,
    AthleteGoal,
    AthleteNotification,
    Alumno,
    CompletedActivity,
    Membership,
    OAuthIntegrationStatus,
    WellnessCheckIn,
    WorkoutAssignment,
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

        # Priority: show PLANNED/MOVED first (still pending). If all are done,
        # still show today's first assignment so the athlete can review their day.
        all_today = (
            WorkoutAssignment.objects.filter(
                organization=org,
                athlete__user=request.user,
                scheduled_date=today,
            )
            .select_related("planned_workout")
            .order_by("day_order")
        )

        # Prefer pending assignment; fall back to first COMPLETED one.
        # CANCELED and SKIPPED are intentionally excluded — they must not appear on "Hoy".
        assignment = (
            all_today.filter(
                status__in=[WorkoutAssignment.Status.PLANNED, WorkoutAssignment.Status.MOVED]
            ).first()
            or all_today.filter(status=WorkoutAssignment.Status.COMPLETED).first()
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

        # ── Weekly summary (PR-148) ──────────────────────────────────────────────
        week_start = today - datetime.timedelta(days=today.weekday())
        _EXCLUDED = [WorkoutAssignment.Status.CANCELED, WorkoutAssignment.Status.SKIPPED]

        week_qs = WorkoutAssignment.objects.filter(
            organization=org,
            athlete__user=request.user,
            scheduled_date__range=(week_start, today),
        ).exclude(status__in=_EXCLUDED)

        sessions_planned = week_qs.count()
        completed_qs = week_qs.filter(status=WorkoutAssignment.Status.COMPLETED)
        sessions_completed = completed_qs.count()

        totals = completed_qs.aggregate(
            total_distance=Sum("actual_distance_meters"),
            total_duration=Sum("actual_duration_seconds"),
        )
        total_km = round((totals["total_distance"] or 0) / 1000, 1)
        total_duration_min = int((totals["total_duration"] or 0) / 60)

        weekly_summary = {
            "sessions_completed": sessions_completed,
            "sessions_planned": sessions_planned,
            "total_km": total_km,
            "total_duration_min": total_duration_min,
        }

        # ── Consecutive days active / streak (PR-148) ────────────────────────
        yesterday = today - datetime.timedelta(days=1)
        completed_dates = list(
            WorkoutAssignment.objects.filter(
                organization=org,
                athlete__user=request.user,
                status=WorkoutAssignment.Status.COMPLETED,
                scheduled_date__lte=yesterday,
            )
            .values_list("scheduled_date", flat=True)
            .distinct()
            .order_by("-scheduled_date")[:366]
        )

        streak = 0
        check = yesterday
        for d in completed_dates:
            if d == check:
                streak += 1
                check = d - datetime.timedelta(days=1)
            else:
                break

        if not has_workout:
            return Response({
                "has_workout": False,
                "weekly_summary": weekly_summary,
                "consecutive_days_active": streak,
            })

        pw = assignment.planned_workout
        return Response(
            {
                "has_workout": True,
                "workout": {
                    "title": pw.name,
                    "description": assignment.coach_notes or pw.description,
                    "date": str(assignment.scheduled_date),
                },
                "weekly_summary": weekly_summary,
                "consecutive_days_active": streak,
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
        membership, org = _resolve_athlete_membership(request.user)

        has_device = _athlete_has_device(request.user)

        pref = AthleteDevicePreference.objects.filter(
            athlete=request.user, organization=org
        ).first()

        dismissed = pref.dismissed if pref else False
        dismissed_reason = pref.dismissed_reason if pref else None

        show_prompt = (not has_device) and (not dismissed)

        unread_count = AthleteNotification.objects.filter(
            recipient=request.user, organization=org, read=False,
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
        membership, org = _resolve_athlete_membership(request.user)

        notifications = AthleteNotification.objects.filter(
            recipient=request.user, organization=org, read=False,
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


# ==============================================================================
# PR-156: Athlete self-serve progress endpoints
# ==============================================================================

def _effective_goal_date(goal):
    """Return the effective target date for a goal (event date or target_date)."""
    if goal.target_event_id and goal.target_event:
        return goal.target_event.event_date
    return goal.target_date


class AthleteGoalsView(APIView):
    """
    GET /api/athlete/goals/

    Returns the authenticated athlete's own active/planned goals sorted by date,
    with a computed days_remaining field.

    403: no active athlete membership.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership, org = _resolve_athlete_membership(request.user)

        athlete_obj = Athlete.objects.filter(user=request.user, organization=org).first()
        if not athlete_obj:
            return Response({"goals": []})

        today = timezone.localdate()
        qs = (
            AthleteGoal.objects
            .filter(
                organization=org,
                athlete=athlete_obj,
                status__in=[AthleteGoal.Status.ACTIVE, AthleteGoal.Status.PLANNED],
            )
            .select_related("target_event")
        )

        goals = []
        for goal in qs:
            effective_date = _effective_goal_date(goal)
            if effective_date is None:
                continue
            days_remaining = (effective_date - today).days
            goals.append({
                "id": goal.id,
                "name": goal.title,
                "date": effective_date.isoformat(),
                "priority": goal.priority,
                "days_remaining": days_remaining,
            })

        goals.sort(key=lambda g: g["date"])
        return Response({"goals": goals})


class AthleteWeeklySummaryView(APIView):
    """
    GET /api/athlete/weekly-summary/

    Returns the athlete's current ISO week summary: sessions, compliance,
    actual totals, streak, and a 7-day completion array.

    403: no active athlete membership.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership, org = _resolve_athlete_membership(request.user)

        today = timezone.localdate()
        week_start = today - datetime.timedelta(days=today.weekday())  # Monday
        week_end = week_start + datetime.timedelta(days=6)  # Sunday

        _EXCLUDED = [WorkoutAssignment.Status.CANCELED, WorkoutAssignment.Status.SKIPPED]

        # Sessions: planned vs completed via WorkoutAssignment
        week_qs = WorkoutAssignment.objects.filter(
            organization=org,
            athlete__user=request.user,
            scheduled_date__range=(week_start, week_end),
        ).exclude(status__in=_EXCLUDED)

        planned_sessions = week_qs.count()
        completed_sessions = week_qs.filter(
            status=WorkoutAssignment.Status.COMPLETED
        ).count()

        compliance_pct = (
            round(completed_sessions / planned_sessions * 100)
            if planned_sessions > 0 else 0
        )

        # Actual totals from CompletedActivity (real device data)
        alumno = Alumno.objects.filter(usuario=request.user).first()
        total_distance_m = 0
        total_duration_s = 0
        total_elevation_m = 0
        if alumno:
            agg = CompletedActivity.objects.filter(
                organization=org,
                alumno=alumno,
                start_time__date__gte=week_start,
                start_time__date__lte=today,
            ).aggregate(
                dist=Sum("distance_m"),
                dur=Sum("duration_s"),
                elev=Sum("elevation_gain_m"),
            )
            total_distance_m = int(agg["dist"] or 0)
            total_duration_s = int(agg["dur"] or 0)
            total_elevation_m = int(agg["elev"] or 0)

        # Streak: consecutive days with a COMPLETED WorkoutAssignment up to yesterday
        yesterday = today - datetime.timedelta(days=1)
        completed_dates = set(
            WorkoutAssignment.objects.filter(
                organization=org,
                athlete__user=request.user,
                status=WorkoutAssignment.Status.COMPLETED,
                scheduled_date__lte=yesterday,
            )
            .values_list("scheduled_date", flat=True)
            .distinct()
        )

        streak = 0
        check = yesterday
        while check in completed_dates:
            streak += 1
            check = check - datetime.timedelta(days=1)

        # 7-day circle array: each day of ISO week (Mon–Sun)
        days_array = []
        completed_today_dates = set(
            WorkoutAssignment.objects.filter(
                organization=org,
                athlete__user=request.user,
                status=WorkoutAssignment.Status.COMPLETED,
                scheduled_date__range=(week_start, today),
            ).values_list("scheduled_date", flat=True)
        )

        for i in range(7):
            day = week_start + datetime.timedelta(days=i)
            days_array.append({
                "date": day.isoformat(),
                "completed": day in completed_today_dates,
            })

        return Response({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "planned_sessions": planned_sessions,
            "completed_sessions": completed_sessions,
            "compliance_pct": compliance_pct,
            "total_distance_m": total_distance_m,
            "total_duration_s": total_duration_s,
            "total_elevation_m": total_elevation_m,
            "streak_days": streak,
            "days": days_array,
        })


class AthleteWellnessTodayView(APIView):
    """
    GET /api/athlete/wellness/today/

    Returns the authenticated athlete's WellnessCheckIn for today if it exists,
    or {"submitted": false} if not.

    403: no active athlete membership.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership, org = _resolve_athlete_membership(request.user)

        today = timezone.localdate()
        athlete_obj = Athlete.objects.filter(user=request.user, organization=org).first()
        if not athlete_obj:
            return Response({"submitted": False})

        checkin = WellnessCheckIn.objects.filter(
            organization=org,
            athlete=athlete_obj,
            date=today,
        ).first()

        if not checkin:
            return Response({"submitted": False})

        return Response({
            "submitted": True,
            "date": checkin.date.isoformat(),
            "sleep_quality": checkin.sleep_quality,
            "mood": checkin.mood,
            "energy": checkin.energy,
            "muscle_soreness": checkin.muscle_soreness,
            "stress": checkin.stress,
        })
