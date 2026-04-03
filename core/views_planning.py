"""
core/views_planning.py — PR-158

Coach planning endpoints:

  GET  /api/coach/athletes/<membership_id>/workout-history/
      Day-by-day grid of the last 6 weeks of workout assignments for a single
      athlete. Includes repetition alerts (same workout N consecutive weeks).

  GET  /api/p1/orgs/<org_id>/group-workout-history/
      Same grid but aggregated across a team (workouts assigned to the group,
      keyed by source week and day).

  POST /api/p1/orgs/<org_id>/copy-week/
      Copies all WorkoutAssignments from a source week to a target week for
      all athletes in a team (or a subset). Idempotent.

  GET  /api/coach/athletes/<membership_id>/estimated-weekly-load/
      Returns planned TSS + phase + recommended range for a target week.
      Used for real-time load feedback while planning.

Athlete-side:

  GET  /api/athlete/plan-vs-real/
      Weekly plan vs real compliance summary with per-session breakdown.
      Used by AthleteMyTraining to show compliance bars and badges.

Tenancy: all queries filter by organization. Coach endpoints validate
membership_id/org_id belong to the coach's org. Fail-closed on every query.
"""

import datetime
import logging

from django.db import IntegrityError
from django.db.models import Avg, Sum
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Athlete,
    CompletedActivity,
    DailyLoad,
    Membership,
    Organization,
    PlannedWorkout,
    Team,
    TrainingWeek,
    WorkoutAssignment,
)
from core.tenancy import OrgTenantMixin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers (mirrored from views_periodization.py to avoid circular import)
# ---------------------------------------------------------------------------

def _get_coach_membership(request):
    """Resolve the requesting user's active coach/owner Membership."""
    memberships = list(
        Membership.objects.select_related("organization").filter(
            user=request.user,
            role__in=[Membership.Role.OWNER, Membership.Role.COACH],
            is_active=True,
        )
    )
    if not memberships:
        raise PermissionDenied("No active coach or owner membership found.")
    if len(memberships) == 1:
        return memberships[0]
    query_params = getattr(request, "query_params", request.GET)
    org_id = query_params.get("org_id")
    if not org_id:
        raise ValidationError(
            {"org_id": "Multiple coach memberships found. Provide ?org_id= to specify."}
        )
    try:
        org_id = int(org_id)
    except (TypeError, ValueError):
        raise ValidationError({"org_id": "Must be an integer."})
    matched = [m for m in memberships if m.organization_id == org_id]
    if not matched:
        raise PermissionDenied("No active coach membership in the specified organization.")
    return matched[0]


def _resolve_athlete_from_membership(membership_id: int, org) -> Athlete:
    """
    Resolve an Athlete from an athlete Membership PK.
    Fail-closed: membership must exist, belong to org, role=athlete.
    """
    try:
        m = Membership.objects.select_related("user").get(
            pk=membership_id,
            organization=org,
            role=Membership.Role.ATHLETE,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise NotFound("Athlete membership not found in this organization.")

    athlete = Athlete.objects.filter(user=m.user, organization=org).first()
    if not athlete:
        raise NotFound("Athlete record not found for this membership.")
    return athlete


def _monday(date: datetime.date) -> datetime.date:
    """Return the Monday of the week containing date."""
    return date - datetime.timedelta(days=date.weekday())


DAY_LABELS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Phase-based TSS recommendations as fraction of average weekly TSS
PHASE_LOAD_RANGE = {
    "carga":    (0.80, 1.00),
    "descarga": (0.50, 0.70),
    "carrera":  (0.30, 0.50),
    "descanso": (0.00, 0.30),
    "lesion":   (0.00, 0.15),
}

# Estimated TSS per hour if planned_tss not set (conservative estimate)
_TSS_PER_HOUR_ESTIMATE = 50.0


def _build_day_grid(assignments_qs, week_start: datetime.date) -> list[dict]:
    """Build a 7-element day grid for a single week from an assignment queryset."""
    by_date: dict[datetime.date, list[dict]] = {}
    for a in assignments_qs:
        pw = a.planned_workout
        entry = {
            "title": pw.name if pw else "Sin nombre",
            "sport": (pw.discipline.upper() if pw and pw.discipline else "OTHER"),
            "duration_min": (
                round(pw.estimated_duration_seconds / 60)
                if pw and pw.estimated_duration_seconds
                else None
            ),
            "distance_km": (
                round(pw.estimated_distance_meters / 1000, 1)
                if pw and pw.estimated_distance_meters
                else None
            ),
            "planned_tss": pw.planned_tss if pw else None,
        }
        by_date.setdefault(a.scheduled_date, []).append(entry)

    days = []
    for offset in range(7):
        day = week_start + datetime.timedelta(days=offset)
        days.append({
            "date": day.isoformat(),
            "day": DAY_LABELS[offset],
            "workouts": by_date.get(day, []),
        })
    return days


def _week_summary(days: list[dict]) -> dict:
    """Compute aggregate summary for a week's day grid."""
    sessions = 0
    distance_km = 0.0
    duration_min = 0
    for d in days:
        sessions += len(d["workouts"])
        for w in d["workouts"]:
            distance_km += w.get("distance_km") or 0
            duration_min += w.get("duration_min") or 0
    return {
        "sessions": sessions,
        "distance_km": round(distance_km, 1),
        "duration_min": duration_min,
    }


def _detect_repetitions(week_list: list[dict]) -> list[dict]:
    """
    Detect workout names that appear in consecutive weeks.
    week_list: list of {"week_start": str, "days": [...]}
    Returns repetition alerts for names with >= 2 consecutive weeks.
    """
    # Collect unique names per week
    week_names: list[set[str]] = []
    for wk in week_list:
        names: set[str] = set()
        for day in wk.get("days", []):
            for wo in day.get("workouts", []):
                if wo.get("title"):
                    names.add(wo["title"])
        week_names.append(names)

    all_names: set[str] = set()
    for ns in week_names:
        all_names.update(ns)

    alerts = []
    for name in sorted(all_names):
        max_consec = 0
        consec = 0
        for ns in week_names:
            if name in ns:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        if max_consec >= 2:
            severity = "warning" if max_consec >= 4 else "info"
            alerts.append({
                "workout": name,
                "consecutive_weeks": max_consec,
                "severity": severity,
            })
    return alerts


# ---------------------------------------------------------------------------
# A1: Individual athlete workout history (day-by-day grid)
# ---------------------------------------------------------------------------

class WorkoutHistoryView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/workout-history/
        ?weeks=6&target_week=2026-04-06

    Returns last N weeks of assignments for a single athlete in day-by-day
    grid format. target_week (Monday) shifts the window; defaults to today's
    Monday as the last week.

    Response:
        {
            "athlete_name": str,
            "weeks": [
                {
                    "week_number": int,
                    "week_start": "YYYY-MM-DD",
                    "days": [{"date": str, "day": str, "workouts": [...]}],
                    "summary": {"sessions": int, "distance_km": float, "duration_min": int}
                }
            ],
            "repetition_alerts": [{"workout": str, "consecutive_weeks": int, "severity": str}]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        coach_membership = _get_coach_membership(request)
        org = coach_membership.organization
        athlete = _resolve_athlete_from_membership(membership_id, org)

        try:
            weeks = int(request.query_params.get("weeks", 6))
        except (TypeError, ValueError):
            weeks = 6
        weeks = max(1, min(26, weeks))

        target_week_str = request.query_params.get("target_week")
        if target_week_str:
            try:
                target_monday = _monday(datetime.date.fromisoformat(target_week_str))
            except ValueError:
                target_monday = _monday(datetime.date.today())
        else:
            target_monday = _monday(datetime.date.today())

        start_date = target_monday - datetime.timedelta(weeks=weeks - 1)
        end_date = target_monday + datetime.timedelta(days=6)

        assignments = (
            WorkoutAssignment.objects
            .filter(
                organization=org,
                athlete=athlete,
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date,
            )
            .select_related("planned_workout")
            .order_by("scheduled_date", "day_order")
        )

        # Group assignments by week_start
        by_week: dict[datetime.date, list] = {}
        for a in assignments:
            wk = _monday(a.scheduled_date)
            by_week.setdefault(wk, []).append(a)

        week_list = []
        for i in range(weeks):
            wk = start_date + datetime.timedelta(weeks=i)
            week_assignments = by_week.get(wk, [])
            days = _build_day_grid(week_assignments, wk)
            iso_week = _iso_week_number(wk)
            week_list.append({
                "week_number": iso_week,
                "week_start": wk.isoformat(),
                "days": days,
                "summary": _week_summary(days),
            })

        athlete_name = (
            athlete.user.get_full_name() or athlete.user.username
            if athlete.user_id else f"Atleta #{athlete.pk}"
        )

        return Response({
            "athlete_name": athlete_name,
            "weeks": week_list,
            "repetition_alerts": _detect_repetitions(week_list),
        })


def _iso_week_number(date: datetime.date) -> int:
    """Return ISO week number for a date."""
    # ISO: week containing the Thursday of that week
    d = date
    dow = d.isoweekday()  # Mon=1 … Sun=7
    d = d + datetime.timedelta(days=4 - dow)  # shift to Thursday
    year_start = datetime.date(d.year, 1, 1)
    return (d - year_start).days // 7 + 1


# ---------------------------------------------------------------------------
# A1b: Group workout history (aggregated for a team)
# ---------------------------------------------------------------------------

class GroupWorkoutHistoryView(OrgTenantMixin, APIView):
    """
    GET /api/p1/orgs/<org_id>/group-workout-history/
        ?weeks=6&target_week=2026-04-06&team_id=1

    Returns last N weeks of assignments for a team (bulk assignments shared by
    the group). Aggregates unique workouts assigned across the team per day.

    Response: same shape as WorkoutHistoryView but athlete_name is replaced
    by team_name and represents the group.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id: int):
        if self.membership.role not in ("owner", "coach"):
            raise PermissionDenied("Coach or owner required.")

        org = self.organization

        try:
            weeks = int(request.query_params.get("weeks", 6))
        except (TypeError, ValueError):
            weeks = 6
        weeks = max(1, min(26, weeks))

        target_week_str = request.query_params.get("target_week")
        if target_week_str:
            try:
                target_monday = _monday(datetime.date.fromisoformat(target_week_str))
            except ValueError:
                target_monday = _monday(datetime.date.today())
        else:
            target_monday = _monday(datetime.date.today())

        team_id = request.query_params.get("team_id")
        team_name = "Todos los atletas"
        if team_id:
            try:
                team = Team.objects.get(pk=int(team_id), organization=org)
                team_name = team.name
            except Team.DoesNotExist:
                raise NotFound("Team not found in this organization.")

        start_date = target_monday - datetime.timedelta(weeks=weeks - 1)
        end_date = target_monday + datetime.timedelta(days=6)

        qs = WorkoutAssignment.objects.filter(
            organization=org,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        ).select_related("planned_workout", "athlete")

        if team_id:
            qs = qs.filter(athlete__team_id=int(team_id))

        # Group by week_start + date, deduplicate by workout name per day
        # (group assignments share the same workouts)
        by_week: dict[datetime.date, dict[datetime.date, set[str]]] = {}
        for a in qs:
            wk = _monday(a.scheduled_date)
            pw = a.planned_workout
            name = pw.name if pw else "Sin nombre"
            by_week.setdefault(wk, {}).setdefault(a.scheduled_date, set()).add(name)

        week_list = []
        for i in range(weeks):
            wk = start_date + datetime.timedelta(weeks=i)
            days_data = by_week.get(wk, {})
            days = []
            for offset in range(7):
                day = wk + datetime.timedelta(days=offset)
                names = days_data.get(day, set())
                days.append({
                    "date": day.isoformat(),
                    "day": DAY_LABELS[offset],
                    "workouts": [{"title": n} for n in sorted(names)],
                })
            week_list.append({
                "week_number": _iso_week_number(wk),
                "week_start": wk.isoformat(),
                "days": days,
                "summary": _week_summary(days),
            })

        return Response({
            "team_name": team_name,
            "weeks": week_list,
            "repetition_alerts": _detect_repetitions(week_list),
        })


# ---------------------------------------------------------------------------
# A2: Copy week
# ---------------------------------------------------------------------------

class CopyWeekView(OrgTenantMixin, APIView):
    """
    POST /api/p1/orgs/<org_id>/copy-week/

    Copies all WorkoutAssignments from source_week_start to target_week_start
    for athletes in a team (or a list of athlete_ids). Idempotent: running
    twice does not create duplicates (uses get_or_create on unique constraint).

    Body:
        {
            "source_week_start": "YYYY-MM-DD",  # Monday of source week
            "target_week_start": "YYYY-MM-DD",  # Monday of target week
            "team_id": 1,                        # optional; null = all athletes
            "athlete_ids": null                  # optional list of Athlete PKs
        }

    Response:
        { "copied": int, "athletes_affected": int, "workouts": [str, ...] }
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def post(self, request, org_id: int):
        if self.membership.role not in ("owner", "coach"):
            raise PermissionDenied("Coach or owner required.")

        org = self.organization
        data = request.data

        # Parse and validate source/target weeks
        try:
            source_monday = _monday(datetime.date.fromisoformat(
                data.get("source_week_start", "")
            ))
        except (TypeError, ValueError):
            raise ValidationError({"source_week_start": "Must be a valid date (YYYY-MM-DD)."})

        try:
            target_monday = _monday(datetime.date.fromisoformat(
                data.get("target_week_start", "")
            ))
        except (TypeError, ValueError):
            raise ValidationError({"target_week_start": "Must be a valid date (YYYY-MM-DD)."})

        if source_monday == target_monday:
            raise ValidationError({"target_week_start": "Target week must differ from source week."})

        team_id = data.get("team_id")
        athlete_ids = data.get("athlete_ids")  # optional list of Athlete PKs

        # Resolve athlete set (organization-scoped)
        athletes_qs = Athlete.objects.filter(organization=org, is_active=True)
        if athlete_ids:
            athletes_qs = athletes_qs.filter(pk__in=athlete_ids)
        elif team_id:
            athletes_qs = athletes_qs.filter(team_id=team_id)

        athlete_id_set = set(athletes_qs.values_list("pk", flat=True))
        if not athlete_id_set:
            return Response({"copied": 0, "athletes_affected": 0, "workouts": []})

        # Fetch source week assignments
        source_end = source_monday + datetime.timedelta(days=6)
        source_assignments = (
            WorkoutAssignment.objects
            .filter(
                organization=org,
                athlete_id__in=athlete_id_set,
                scheduled_date__gte=source_monday,
                scheduled_date__lte=source_end,
            )
            .select_related("planned_workout")
        )

        delta = target_monday - source_monday
        copied_count = 0
        athletes_affected: set[int] = set()
        workout_names: set[str] = set()

        for src in source_assignments:
            new_date = src.scheduled_date + delta
            pw_name = src.planned_workout.name if src.planned_workout_id else "Sin nombre"
            try:
                _, created = WorkoutAssignment.objects.get_or_create(
                    organization=org,
                    athlete_id=src.athlete_id,
                    scheduled_date=new_date,
                    day_order=src.day_order,
                    defaults={
                        "planned_workout_id": src.planned_workout_id,
                        "assigned_by": request.user,
                        "coach_notes": src.coach_notes,
                        "status": WorkoutAssignment.Status.PLANNED,
                        "snapshot_version": src.snapshot_version,
                        "target_zone_override": src.target_zone_override,
                        "target_pace_override": src.target_pace_override,
                        "target_rpe_override": src.target_rpe_override,
                        "target_power_override": src.target_power_override,
                    },
                )
                if created:
                    copied_count += 1
                    athletes_affected.add(src.athlete_id)
                    workout_names.add(pw_name)
            except IntegrityError:
                # Race condition: already exists (noop)
                pass

        logger.info(
            "copy_week.completed",
            extra={
                "event_name": "copy_week.completed",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "source_week": source_monday.isoformat(),
                "target_week": target_monday.isoformat(),
                "copied": copied_count,
                "athletes_affected": len(athletes_affected),
            },
        )

        return Response({
            "copied": copied_count,
            "athletes_affected": len(athletes_affected),
            "workouts": sorted(workout_names),
        })


# ---------------------------------------------------------------------------
# A3: Estimated weekly load for a single athlete
# ---------------------------------------------------------------------------

class EstimatedWeeklyLoadView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/estimated-weekly-load/
        ?week_start=2026-04-06

    Returns the planned TSS and phase recommendation for a target week.

    Response:
        {
            "planned_tss": float,
            "planned_sessions": int,
            "planned_distance_km": float,
            "planned_duration_min": int,
            "current_phase": str | null,
            "athlete_avg_weekly_tss": float | null,
            "recommended_tss_range": {"min": float, "max": float} | null,
            "load_status": "ok" | "over" | "under",
            "load_message": str | null,
            "vs_previous_week": {"previous_tss": float, "change_pct": float} | null
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        coach_membership = _get_coach_membership(request)
        org = coach_membership.organization
        athlete = _resolve_athlete_from_membership(membership_id, org)

        week_str = request.query_params.get("week_start")
        if week_str:
            try:
                target_monday = _monday(datetime.date.fromisoformat(week_str))
            except ValueError:
                target_monday = _monday(datetime.date.today())
        else:
            target_monday = _monday(datetime.date.today())

        target_end = target_monday + datetime.timedelta(days=6)

        # Planned assignments for target week
        assignments = (
            WorkoutAssignment.objects
            .filter(
                organization=org,
                athlete=athlete,
                scheduled_date__gte=target_monday,
                scheduled_date__lte=target_end,
            )
            .select_related("planned_workout")
        )

        planned_tss = 0.0
        planned_distance_km = 0.0
        planned_duration_min = 0
        planned_sessions = 0

        for a in assignments:
            pw = a.planned_workout
            if not pw:
                continue
            planned_sessions += 1
            if pw.planned_tss:
                planned_tss += pw.planned_tss
            elif pw.estimated_duration_seconds:
                planned_tss += (pw.estimated_duration_seconds / 3600) * _TSS_PER_HOUR_ESTIMATE
            if pw.estimated_distance_meters:
                planned_distance_km += pw.estimated_distance_meters / 1000
            if pw.estimated_duration_seconds:
                planned_duration_min += pw.estimated_duration_seconds // 60

        # Current phase from TrainingWeek
        training_week = TrainingWeek.objects.filter(
            organization=org,
            athlete=athlete,
            week_start=target_monday,
        ).first()
        current_phase = training_week.phase if training_week else None

        # Average weekly TSS from last 4 weeks of DailyLoad
        four_weeks_ago = target_monday - datetime.timedelta(weeks=4)
        avg_tss_result = (
            DailyLoad.objects
            .filter(
                organization=org,
                athlete=athlete.user,
                date__gte=four_weeks_ago,
                date__lt=target_monday,
            )
            .aggregate(total_tss=Sum("tss"))
        )
        total_raw = avg_tss_result.get("total_tss") or 0
        avg_weekly_tss = round(total_raw / 4, 1) if total_raw > 0 else None

        # Recommended TSS range based on phase
        recommended_range = None
        load_status = "ok"
        load_message = None

        if avg_weekly_tss and current_phase and current_phase in PHASE_LOAD_RANGE:
            lo_frac, hi_frac = PHASE_LOAD_RANGE[current_phase]
            rec_min = round(avg_weekly_tss * lo_frac, 0)
            rec_max = round(avg_weekly_tss * hi_frac, 0)
            recommended_range = {"min": rec_min, "max": rec_max}

            if planned_tss > rec_max and rec_max > 0:
                over_pct = round((planned_tss - rec_max) / rec_max * 100)
                load_status = "over"
                phase_label = {
                    "carga": "carga", "descarga": "descarga",
                    "carrera": "competencia", "descanso": "descanso", "lesion": "lesión",
                }.get(current_phase, current_phase)
                load_message = (
                    f"Carga planificada supera la recomendada para {phase_label} (+{over_pct}%)"
                )
            elif planned_tss < rec_min and rec_min > 0:
                under_pct = round((rec_min - planned_tss) / rec_min * 100)
                load_status = "under"
                load_message = (
                    f"Carga planificada está por debajo de lo recomendado (-{under_pct}%)"
                )

        # Compare to previous week actual TSS (from DailyLoad)
        prev_monday = target_monday - datetime.timedelta(weeks=1)
        prev_end = target_monday - datetime.timedelta(days=1)
        prev_result = (
            DailyLoad.objects
            .filter(
                organization=org,
                athlete=athlete.user,
                date__gte=prev_monday,
                date__lte=prev_end,
            )
            .aggregate(total_tss=Sum("tss"))
        )
        prev_tss = prev_result.get("total_tss") or 0
        vs_previous = None
        if prev_tss > 0 and planned_tss is not None:
            change_pct = round((planned_tss - prev_tss) / prev_tss * 100)
            vs_previous = {"previous_tss": round(prev_tss, 1), "change_pct": change_pct}

        return Response({
            "planned_tss": round(planned_tss, 1),
            "planned_sessions": planned_sessions,
            "planned_distance_km": round(planned_distance_km, 1),
            "planned_duration_min": planned_duration_min,
            "current_phase": current_phase,
            "athlete_avg_weekly_tss": avg_weekly_tss,
            "recommended_tss_range": recommended_range,
            "load_status": load_status,
            "load_message": load_message,
            "vs_previous_week": vs_previous,
        })


# ---------------------------------------------------------------------------
# A4: Athlete plan vs real weekly summary
# ---------------------------------------------------------------------------

def _resolve_athlete_membership(user):
    """Return (membership, org, athlete) for an athlete user. 403 if not found."""
    try:
        m = Membership.objects.select_related("organization").get(
            user=user,
            is_active=True,
            role=Membership.Role.ATHLETE,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active athlete membership found.")
    org = m.organization
    athlete = Athlete.objects.filter(user=user, organization=org).first()
    return m, org, athlete


class AthletePlanVsRealView(APIView):
    """
    GET /api/athlete/plan-vs-real/?week_start=2026-03-30

    Returns weekly plan vs real compliance with per-session breakdown.

    Response:
        {
            "week_start": "YYYY-MM-DD",
            "planned": {"sessions": int, "distance_km": float, "duration_min": int, "elevation_m": int},
            "actual": {"sessions": int, "distance_km": float, "duration_min": int, "elevation_m": int},
            "compliance_pct": int | null,
            "per_session": [
                {
                    "date": "YYYY-MM-DD",
                    "workout": str | null,
                    "planned_km": float | null,
                    "actual_km": float | null,
                    "compliance_pct": int | null,
                    "completed": bool
                }
            ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, org, athlete = _resolve_athlete_membership(request.user)

        week_str = request.query_params.get("week_start")
        if week_str:
            try:
                week_monday = _monday(datetime.date.fromisoformat(week_str))
            except ValueError:
                week_monday = _monday(datetime.date.today())
        else:
            week_monday = _monday(datetime.date.today())

        week_end = week_monday + datetime.timedelta(days=6)

        # Fetch all assignments for this week
        assignments = list(
            WorkoutAssignment.objects
            .filter(
                organization=org,
                athlete=athlete,
                scheduled_date__gte=week_monday,
                scheduled_date__lte=week_end,
            )
            .select_related("planned_workout")
            .order_by("scheduled_date", "day_order")
        ) if athlete else []

        # Fetch completed activities for this week
        activities_by_date: dict[datetime.date, list] = {}
        if athlete:
            completed = CompletedActivity.objects.filter(
                organization=org,
                athlete=athlete,
                start_time__date__gte=week_monday,
                start_time__date__lte=week_end,
            )
            for act in completed:
                day = act.start_time.date()
                activities_by_date.setdefault(day, []).append(act)

        # Build per-session rows
        per_session = []
        total_planned_km = 0.0
        total_planned_min = 0
        total_planned_elev = 0
        total_actual_km = 0.0
        total_actual_min = 0
        total_actual_elev = 0
        actual_sessions = 0

        for a in assignments:
            pw = a.planned_workout
            planned_km = (
                round(pw.estimated_distance_meters / 1000, 2)
                if pw and pw.estimated_distance_meters else None
            )
            planned_min = (
                pw.estimated_duration_seconds // 60
                if pw and pw.estimated_duration_seconds else None
            )
            planned_elev = pw.elevation_gain_min_m if pw else None

            is_completed = a.status == WorkoutAssignment.Status.COMPLETED
            actual_km = None
            compliance_pct = None

            if is_completed:
                # Use actual data from assignment (self-reported or synced)
                if a.actual_distance_meters is not None:
                    actual_km = round(a.actual_distance_meters / 1000, 2)
                elif a.actual_duration_seconds is not None:
                    # Estimate from duration if no distance
                    actual_km = None

                actual_min = (
                    a.actual_duration_seconds // 60
                    if a.actual_duration_seconds is not None else None
                )
                actual_elev = a.actual_elevation_gain

                # Compliance: distance-based if available, else duration-based
                if planned_km and actual_km is not None:
                    compliance_pct = min(150, round(actual_km / planned_km * 100))
                elif planned_min and actual_min is not None:
                    compliance_pct = min(150, round(actual_min / planned_min * 100))

                actual_sessions += 1
                total_actual_km += actual_km or 0
                total_actual_min += actual_min or 0
                total_actual_elev += actual_elev or 0

            total_planned_km += planned_km or 0
            total_planned_min += planned_min or 0
            total_planned_elev += planned_elev or 0

            per_session.append({
                "date": a.scheduled_date.isoformat(),
                "workout": pw.name if pw else None,
                "planned_km": planned_km,
                "actual_km": actual_km,
                "compliance_pct": compliance_pct,
                "completed": is_completed,
            })

        # Overall compliance
        overall_compliance = None
        if assignments:
            completed_count = sum(1 for a in assignments if a.status == WorkoutAssignment.Status.COMPLETED)
            overall_compliance = round(completed_count / len(assignments) * 100)

        return Response({
            "week_start": week_monday.isoformat(),
            "planned": {
                "sessions": len(assignments),
                "distance_km": round(total_planned_km, 1),
                "duration_min": total_planned_min,
                "elevation_m": total_planned_elev,
            },
            "actual": {
                "sessions": actual_sessions,
                "distance_km": round(total_actual_km, 1),
                "duration_min": total_actual_min,
                "elevation_m": total_actual_elev,
            },
            "compliance_pct": overall_compliance,
            "per_session": per_session,
        })
