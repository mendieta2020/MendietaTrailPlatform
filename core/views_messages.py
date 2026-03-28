"""
core/views_messages.py — PR-147: Smart Alerts & Internal Messaging

Endpoints:
  POST /api/p1/orgs/<org_id>/messages/          — send message (coach only)
  GET  /api/p1/orgs/<org_id>/messages/          — list messages (scoped by role)
  PATCH /api/p1/orgs/<org_id>/messages/<id>/read/ — mark as read (recipient only)
  GET  /api/p1/orgs/<org_id>/athletes/<athlete_id>/alerts/ — compute alerts

Tenancy enforcement: all views use OrgTenantMixin (fail-closed, Law 1).
"""

import datetime
import logging

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Athlete,
    InternalMessage,
    Membership,
    WorkoutAssignment,
)
from core.tenancy import OrgTenantMixin

logger = logging.getLogger(__name__)

_WRITE_ROLES = {"owner", "admin", "coach"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_athlete_or_404(org, athlete_id):
    try:
        return Athlete.objects.get(pk=athlete_id, organization=org, is_active=True)
    except Athlete.DoesNotExist:
        raise NotFound("Athlete not found in this organization.")


def _message_to_dict(msg):
    return {
        "id": msg.pk,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender.get_full_name() or msg.sender.username,
        "recipient_id": msg.recipient_id,
        "content": msg.content,
        "alert_type": msg.alert_type,
        "whatsapp_sent": msg.whatsapp_sent,
        "read_at": msg.read_at.isoformat() if msg.read_at else None,
        "created_at": msg.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Message list / create
# ---------------------------------------------------------------------------

class InternalMessageListCreateView(OrgTenantMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id):
        from django.db.models import Q  # noqa: PLC0415

        qs = (
            InternalMessage.objects.filter(
                organization=self.organization,
            )
            # All roles: show only their own conversation thread (sent or received)
            .filter(Q(recipient=request.user) | Q(sender=request.user))
            .select_related("sender", "recipient")
            .order_by("-created_at")
        )

        messages = [_message_to_dict(m) for m in qs[:50]]

        # Unread count for this user (drives notification bell badge)
        unread_count = InternalMessage.objects.filter(
            organization=self.organization,
            recipient=request.user,
            read_at__isnull=True,
        ).count()

        # Coaches list — for athletes starting a new thread (not needed for coaches)
        coaches = []
        if self.membership.role == "athlete":
            coach_memberships = (
                Membership.objects.filter(
                    organization=self.organization,
                    role__in=_WRITE_ROLES,
                    is_active=True,
                )
                .select_related("user")
                .order_by("user__first_name")
            )
            coaches = [
                {
                    "user_id": m.user_id,
                    "name": m.user.get_full_name() or m.user.username,
                }
                for m in coach_memberships
            ]

        return Response({"results": messages, "coaches": coaches, "unread_count": unread_count})

    def post(self, request, org_id):
        recipient_id = request.data.get("recipient_id")
        content = request.data.get("content", "").strip()
        alert_type = request.data.get("alert_type", "")
        whatsapp_sent = bool(request.data.get("whatsapp_sent", False))

        if not recipient_id:
            raise DRFValidationError({"recipient_id": "This field is required."})
        if not content:
            raise DRFValidationError({"content": "Message content cannot be empty."})

        is_coach = self.membership.role in _WRITE_ROLES
        is_athlete = self.membership.role == "athlete"

        if is_coach:
            # Coach → athlete: recipient must be an active athlete in this org
            if not Membership.objects.filter(
                user_id=recipient_id,
                organization=self.organization,
                role="athlete",
                is_active=True,
            ).exists():
                raise DRFValidationError(
                    {"recipient_id": "Recipient is not an active athlete in this organization."}
                )
        elif is_athlete:
            # Athlete → coach: recipient must be an active coach/admin/owner in this org
            if not Membership.objects.filter(
                user_id=recipient_id,
                organization=self.organization,
                role__in=_WRITE_ROLES,
                is_active=True,
            ).exists():
                raise DRFValidationError(
                    {"recipient_id": "You can only reply to a coach in your organization."}
                )
        else:
            raise PermissionDenied("Only org members can send messages.")

        msg = InternalMessage.objects.create(
            organization=self.organization,
            sender=request.user,
            recipient_id=recipient_id,
            content=content,
            alert_type=alert_type,
            whatsapp_sent=whatsapp_sent,
        )
        msg.refresh_from_db()
        msg.sender  # force select so get_full_name works
        msg = InternalMessage.objects.select_related("sender", "recipient").get(pk=msg.pk)

        logger.info(
            "internal_message_sent",
            extra={
                "event_name": "internal_message_sent",
                "organization_id": self.organization.pk,
                "sender_id": request.user.pk,
                "recipient_id": recipient_id,
                "alert_type": alert_type,
            },
        )
        return Response(_message_to_dict(msg), status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Mark message as read
# ---------------------------------------------------------------------------

class InternalMessageMarkReadView(OrgTenantMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def patch(self, request, org_id, pk):
        try:
            msg = InternalMessage.objects.get(
                pk=pk,
                organization=self.organization,
            )
        except InternalMessage.DoesNotExist:
            raise NotFound("Message not found.")

        if msg.recipient != request.user:
            raise PermissionDenied("Only the recipient can mark a message as read.")

        if msg.read_at is None:
            msg.read_at = timezone.now()
            msg.save(update_fields=["read_at"])

        return Response({"id": msg.pk, "read_at": msg.read_at.isoformat()})


# ---------------------------------------------------------------------------
# Athlete Alerts
# ---------------------------------------------------------------------------

ALERT_MESSAGES = {
    "inactive_4d": (
        "Hola {nombre}, hace {days_count} días que no completás entrenamientos. "
        "¿Todo bien? Contame qué pasó."
    ),
    "acwr_spike": (
        "Hola {nombre}, esta semana entrenaste un {pct}% más de lo habitual. "
        "Riesgo de sobrecarga elevado. La próxima semana reducimos el volumen."
    ),
    "overload_sustained": (
        "Hola {nombre}, llevas varios días superando el plan. "
        "Excelente compromiso, pero ojo con el cuerpo. Revisamos la próxima semana juntos."
    ),
    "monotony": (
        "Hola {nombre}, llevás varios días con la misma intensidad. "
        "Vamos a variar el estímulo para que el cuerpo siga adaptándose."
    ),
    "no_plan": None,  # internal alert for coach only
    "streak_positive": (
        "¡{nombre}! Completaste {days_count} días seguidos. "
        "Eso es disciplina de élite. Seguí así 💪"
    ),
}

ALERT_SEVERITY = {
    "inactive_4d": "warning",
    "acwr_spike": "danger",
    "overload_sustained": "info",
    "monotony": "info",
    "no_plan": "warning",
    "streak_positive": "success",
}


class AthleteAlertsView(OrgTenantMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id, athlete_id):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches can view athlete alerts.")

        athlete = _get_athlete_or_404(self.organization, athlete_id)
        athlete_name = athlete.user.get_full_name() or athlete.user.username
        first_name = athlete.user.first_name or athlete_name

        today = datetime.date.today()
        alerts = []

        # ── Window: last 28 days + next 7 ───────────────────────────────────
        past_28_start = today - datetime.timedelta(days=28)
        next_7_end = today + datetime.timedelta(days=7)

        assignments = list(
            WorkoutAssignment.objects.filter(
                organization=self.organization,
                athlete=athlete,
                scheduled_date__gte=past_28_start,
                scheduled_date__lte=next_7_end,
            ).select_related("planned_workout").order_by("scheduled_date")
        )

        past_assignments = [a for a in assignments if a.scheduled_date <= today]
        future_assignments = [a for a in assignments if a.scheduled_date > today]

        # ── 1. inactive_4d ───────────────────────────────────────────────────
        # Count consecutive days (from most-recent assignment date backward)
        # where assignment exists but status != COMPLETED.
        # NOTE: we start from the most recent assignment date, NOT necessarily
        # today, so a gap between the last assignment and today doesn't mask
        # an existing inactive streak.
        consecutive_inactive = 0
        past_by_date = {}
        for a in past_assignments:
            past_by_date.setdefault(a.scheduled_date, []).append(a)

        if past_by_date:
            most_recent = max(past_by_date.keys())
            check_date = most_recent
            while check_date >= past_28_start:
                day_assignments = past_by_date.get(check_date, [])
                if not day_assignments:
                    # No assignment on this day → stop streak
                    break
                all_completed = all(
                    a.status == WorkoutAssignment.Status.COMPLETED for a in day_assignments
                )
                if all_completed:
                    break
                consecutive_inactive += 1
                check_date -= datetime.timedelta(days=1)

        if consecutive_inactive >= 4:
            template = ALERT_MESSAGES["inactive_4d"]
            alerts.append({
                "type": "inactive_4d",
                "severity": ALERT_SEVERITY["inactive_4d"],
                "days_count": consecutive_inactive,
                "message_template": template.format(
                    nombre=first_name, days_count=consecutive_inactive
                ),
                "phone_number": athlete.phone_number,
            })

        # ── 2. acwr_spike ───────────────────────────────────────────────────
        # Compare this week's completed duration vs avg of prior 4 weeks.
        this_week_monday = today - datetime.timedelta(days=today.weekday())
        this_week_duration = sum(
            (a.actual_duration_seconds or 0)
            for a in past_assignments
            if a.scheduled_date >= this_week_monday
            and a.status == WorkoutAssignment.Status.COMPLETED
        )

        weekly_loads = []
        for weeks_back in range(1, 5):
            w_start = this_week_monday - datetime.timedelta(weeks=weeks_back)
            w_end = w_start + datetime.timedelta(days=6)
            week_dur = sum(
                (a.actual_duration_seconds or 0)
                for a in past_assignments
                if w_start <= a.scheduled_date <= w_end
                and a.status == WorkoutAssignment.Status.COMPLETED
            )
            weekly_loads.append(week_dur)

        avg_4wk = sum(weekly_loads) / 4 if any(weekly_loads) else 0

        if avg_4wk > 0 and this_week_duration > avg_4wk * 1.5:
            pct = round((this_week_duration / avg_4wk) * 100)
            template = ALERT_MESSAGES["acwr_spike"]
            alerts.append({
                "type": "acwr_spike",
                "severity": ALERT_SEVERITY["acwr_spike"],
                "days_count": None,
                "pct": pct,
                "message_template": template.format(nombre=first_name, pct=pct),
                "phone_number": athlete.phone_number,
            })

        # ── 3. overload_sustained ───────────────────────────────────────────
        # 5+ consecutive completed days with compliance >= 120%.
        # compliance_pct for a day = avg compliance_color='blue' (>=120%)
        sustained_overload_days = 0
        check_date = today
        while check_date >= past_28_start:
            day_assignments = past_by_date.get(check_date, [])
            if not day_assignments:
                break
            all_overload = all(
                a.status == WorkoutAssignment.Status.COMPLETED
                and a.compliance_color == "blue"
                for a in day_assignments
            )
            if not all_overload:
                break
            sustained_overload_days += 1
            check_date -= datetime.timedelta(days=1)

        if sustained_overload_days >= 5:
            alerts.append({
                "type": "overload_sustained",
                "severity": ALERT_SEVERITY["overload_sustained"],
                "days_count": sustained_overload_days,
                "message_template": ALERT_MESSAGES["overload_sustained"].format(
                    nombre=first_name
                ),
                "phone_number": athlete.phone_number,
            })

        # ── 4. monotony ──────────────────────────────────────────────────────
        # 5+ consecutive completed days with the same session_type.
        consecutive_same_type = 1
        max_monotony = 0
        monotony_type = None
        completed_past = [
            a for a in past_assignments
            if a.status == WorkoutAssignment.Status.COMPLETED
            and a.planned_workout
        ]
        completed_past.sort(key=lambda a: a.scheduled_date)

        if len(completed_past) >= 2:
            for i in range(1, len(completed_past)):
                prev = completed_past[i - 1]
                curr = completed_past[i]
                # Only count consecutive calendar days
                delta = (curr.scheduled_date - prev.scheduled_date).days
                same_type = (
                    curr.planned_workout.session_type == prev.planned_workout.session_type
                )
                if delta == 1 and same_type:
                    consecutive_same_type += 1
                    if consecutive_same_type > max_monotony:
                        max_monotony = consecutive_same_type
                        monotony_type = curr.planned_workout.session_type
                else:
                    consecutive_same_type = 1

        if max_monotony >= 5:
            alerts.append({
                "type": "monotony",
                "severity": ALERT_SEVERITY["monotony"],
                "days_count": max_monotony,
                "session_type": monotony_type,
                "message_template": ALERT_MESSAGES["monotony"].format(
                    nombre=first_name
                ),
                "phone_number": athlete.phone_number,
            })

        # ── 5. no_plan ───────────────────────────────────────────────────────
        # No planned workouts in the next 7 days.
        future_7d = [a for a in future_assignments if a.scheduled_date <= next_7_end]
        if not future_7d:
            alerts.append({
                "type": "no_plan",
                "severity": ALERT_SEVERITY["no_plan"],
                "days_count": None,
                "message_template": None,  # Internal coach alert only
                "phone_number": None,
            })

        # ── 6. streak_positive ───────────────────────────────────────────────
        # 7+ consecutive completed days.
        streak = 0
        check_date = today
        while check_date >= past_28_start:
            day_assignments = past_by_date.get(check_date, [])
            if not day_assignments:
                break
            all_done = all(
                a.status == WorkoutAssignment.Status.COMPLETED for a in day_assignments
            )
            if not all_done:
                break
            streak += 1
            check_date -= datetime.timedelta(days=1)

        if streak >= 7:
            template = ALERT_MESSAGES["streak_positive"]
            alerts.append({
                "type": "streak_positive",
                "severity": ALERT_SEVERITY["streak_positive"],
                "days_count": streak,
                "message_template": template.format(
                    nombre=first_name, days_count=streak
                ),
                "phone_number": athlete.phone_number,
            })

        return Response({
            "athlete_id": athlete.pk,
            "athlete_name": athlete_name,
            "phone_number": athlete.phone_number,
            "alerts": alerts,
        })
