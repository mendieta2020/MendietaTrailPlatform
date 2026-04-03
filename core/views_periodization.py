"""
core/views_periodization.py — PR-157

Views for the auto-periodization feature:

  POST /api/coach/athletes/<membership_id>/auto-periodize/
      Coach triggers auto-periodize for a single athlete.

  POST /api/p1/orgs/<org_id>/auto-periodize-group/
      Coach auto-periodizes all athletes in a team (or entire org).

  GET  /api/coach/athletes/<membership_id>/recent-workouts/?weeks=6
      Coach sees last N weeks of workout titles for an athlete with
      consecutive-repetition warnings.

  GET  /api/athlete/training-phases/?weeks=12
      Athlete sees their own training phases for the next N weeks
      (for the Mi Progreso timeline).

  GET  /api/p1/orgs/<org_id>/athletes/<athlete_id>/training-phases/
      Coach reads an athlete's phases for a date range
      (used for Calendar month-view phase badge).

Tenancy: all queries filter by organization. Coach endpoints validate
membership_id belongs to the coach's org. Fail-closed on every query.
"""

import datetime
import logging

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Athlete,
    Membership,
    Organization,
    TrainingWeek,
    WorkoutAssignment,
)
from core.services_periodization import auto_periodize_athlete, suggest_cycle_pattern
from core.tenancy import OrgTenantMixin

logger = logging.getLogger(__name__)

VALID_PATTERNS = ("1:1", "2:1", "3:1", "4:1")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_coach_membership(request):
    """
    Resolve the requesting user's active coach/owner Membership.
    Mirrors the pattern in views_pmc.py to avoid circular imports.
    """
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
            {"org_id": "Multiple coach memberships found. Provide ?org_id= to specify the organization."}
        )
    try:
        org_id = int(org_id)
    except (TypeError, ValueError):
        raise ValidationError({"org_id": "Must be an integer."})
    matched = [m for m in memberships if m.organization_id == org_id]
    if not matched:
        raise PermissionDenied("No active coach membership found in the specified organization.")
    return matched[0]


def _resolve_athlete_from_membership(membership_id: int, org) -> Athlete:
    """
    Resolve an Athlete object from the athlete's Membership PK.
    Fail-closed: membership must exist, belong to org, have role=athlete.
    Returns Athlete (organization-scoped).
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


# ── A3: Auto-periodize individual athlete ─────────────────────────────────────

class AutoPeriodizeAthleteView(APIView):
    """
    POST /api/coach/athletes/<membership_id>/auto-periodize/

    Generates TrainingWeek records backward from the athlete's active goals.

    Body:
        { "cycle_pattern": "3:1", "weeks_back": 12 }

    Response:
        {
            "athlete_name": str,
            "weeks_created": int,
            "weeks_updated": int,
            "suggested_pattern": str,
            "phases": [{"week_start": "YYYY-MM-DD", "phase": str, "goal"?: str}]
        }

    403: not a coach/owner.
    404: membership not in org.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id: int):
        coach_membership = _get_coach_membership(request)
        org = coach_membership.organization

        athlete = _resolve_athlete_from_membership(membership_id, org)

        cycle_pattern = request.data.get("cycle_pattern", "3:1")
        if cycle_pattern not in VALID_PATTERNS:
            raise ValidationError({"cycle_pattern": f"Must be one of: {VALID_PATTERNS}"})

        try:
            weeks_back = int(request.data.get("weeks_back", 12))
        except (TypeError, ValueError):
            weeks_back = 12
        weeks_back = max(4, min(52, weeks_back))

        result = auto_periodize_athlete(
            athlete=athlete,
            organization=org,
            cycle_pattern=cycle_pattern,
            weeks_back=weeks_back,
        )

        # Compute suggested pattern from athlete's primary goal distance
        from core.models import AthleteGoal
        primary_goal = (
            AthleteGoal.objects
            .filter(
                organization=org,
                athlete=athlete,
                priority=AthleteGoal.Priority.A,
                status__in=[AthleteGoal.Status.ACTIVE, AthleteGoal.Status.PLANNED],
            )
            .first()
        )
        suggested = suggest_cycle_pattern(
            primary_goal.target_distance_km if primary_goal else None
        )

        athlete_name = (
            athlete.user.get_full_name() or athlete.user.username
            if athlete.user_id else f"Atleta #{athlete.pk}"
        )

        return Response({
            "athlete_name": athlete_name,
            "weeks_created": result["weeks_created"],
            "weeks_updated": result["weeks_updated"],
            "suggested_pattern": suggested,
            "phases": result["phases"],
        })


# ── A4: Auto-periodize group ──────────────────────────────────────────────────

class AutoPeriodizeGroupView(OrgTenantMixin, APIView):
    """
    POST /api/p1/orgs/<org_id>/auto-periodize-group/

    Auto-periodizes all athletes in a team (or the entire org if no team_id).
    For each athlete, the cycle pattern is suggested from their primary goal
    distance; the "default_cycle" is used as fallback.

    Body:
        { "team_id": 1 (optional), "default_cycle": "3:1" }

    Response:
        {
            "periodized": int,
            "skipped_no_goals": int,
            "athletes": [{ "athlete_name": str, "cycle": str, "weeks_created": int, "weeks_updated": int }]
        }
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
        default_cycle = request.data.get("default_cycle", "3:1")
        if default_cycle not in VALID_PATTERNS:
            default_cycle = "3:1"
        team_id = request.data.get("team_id")

        athletes_qs = Athlete.objects.filter(organization=org, is_active=True).select_related("user")
        if team_id:
            athletes_qs = athletes_qs.filter(team_id=team_id)

        from core.models import AthleteGoal
        periodized = 0
        skipped_no_goals = 0
        athletes_out = []

        for athlete in athletes_qs:
            # Pick cycle from primary A goal distance
            primary_goal = (
                AthleteGoal.objects
                .filter(
                    organization=org,
                    athlete=athlete,
                    priority=AthleteGoal.Priority.A,
                    status__in=[AthleteGoal.Status.ACTIVE, AthleteGoal.Status.PLANNED],
                )
                .first()
            )
            cycle = suggest_cycle_pattern(
                primary_goal.target_distance_km if primary_goal else None
            ) if primary_goal else default_cycle

            result = auto_periodize_athlete(
                athlete=athlete,
                organization=org,
                cycle_pattern=cycle,
            )

            if result.get("skipped_no_goals"):
                skipped_no_goals += 1
            else:
                periodized += 1
                athlete_name = (
                    athlete.user.get_full_name() or athlete.user.username
                    if athlete.user_id else f"Atleta #{athlete.pk}"
                )
                athletes_out.append({
                    "athlete_name": athlete_name,
                    "cycle": cycle,
                    "weeks_created": result["weeks_created"],
                    "weeks_updated": result["weeks_updated"],
                })

        logger.info(
            "auto_periodize_group.completed",
            extra={
                "event_name": "auto_periodize_group.completed",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "periodized": periodized,
                "skipped_no_goals": skipped_no_goals,
                "team_id": team_id,
            },
        )

        return Response({
            "periodized": periodized,
            "skipped_no_goals": skipped_no_goals,
            "athletes": athletes_out,
        })


# ── A5: Recent workouts endpoint ──────────────────────────────────────────────

class RecentWorkoutsView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/recent-workouts/?weeks=6

    Returns the athlete's last N weeks of assigned workout names,
    grouped by week_start, plus repetition alerts for workouts that appear
    in consecutive weeks.

    Response:
        {
            "weeks": [
                { "week_start": "YYYY-MM-DD", "workouts": ["Name1", "Name2"] },
                ...
            ],
            "repeated_alerts": [
                { "workout": str, "consecutive_weeks": int, "warning": str },
                ...
            ]
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

        today = datetime.date.today()
        today_monday = today - datetime.timedelta(days=today.weekday())
        start_date = today_monday - datetime.timedelta(weeks=weeks)

        # Fetch all assignments for the athlete in the date range
        assignments = (
            WorkoutAssignment.objects
            .filter(
                organization=org,
                athlete=athlete,
                scheduled_date__gte=start_date,
                scheduled_date__lt=today_monday + datetime.timedelta(weeks=1),
            )
            .select_related("planned_workout")
            .order_by("scheduled_date")
        )

        # Group by week_start (Monday)
        week_map: dict[datetime.date, list[str]] = {}
        for a in assignments:
            wk = a.scheduled_date - datetime.timedelta(days=a.scheduled_date.weekday())
            name = a.planned_workout.name if a.planned_workout_id else "Sin nombre"
            week_map.setdefault(wk, [])
            if name not in week_map[wk]:
                week_map[wk].append(name)

        # Build sorted week list covering all N weeks (including empty)
        result_weeks = []
        for i in range(weeks + 1):  # +1 to include current week
            wk = today_monday - datetime.timedelta(weeks=weeks - i)
            result_weeks.append({
                "week_start": wk.isoformat(),
                "workouts": week_map.get(wk, []),
            })

        # Detect consecutive repetitions
        # For each workout name, find how many consecutive weeks it appears in
        all_workout_names: set[str] = set()
        for wk in result_weeks:
            all_workout_names.update(wk["workouts"])

        repeated_alerts = []
        for name in sorted(all_workout_names):
            consecutive = 0
            max_consecutive = 0
            for wk in result_weeks:
                if name in wk["workouts"]:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0

            if max_consecutive >= 2:
                repeated_alerts.append({
                    "workout": name,
                    "consecutive_weeks": max_consecutive,
                    "warning": f"Se repite {max_consecutive} semanas seguidas",
                })

        return Response({
            "weeks": result_weeks,
            "repeated_alerts": repeated_alerts,
        })


# ── Athlete-side: training phases for Mi Progreso timeline ────────────────────

def _resolve_athlete_membership_view(user):
    """Return (membership, org) for an athlete user. 403 if not athlete."""
    try:
        m = Membership.objects.select_related("organization").get(
            user=user,
            is_active=True,
            role=Membership.Role.ATHLETE,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active athlete membership found.")
    return m, m.organization


class AthleteTrainingPhasesView(APIView):
    """
    GET /api/athlete/training-phases/?weeks=12

    Returns the authenticated athlete's own TrainingWeek records for
    the next N weeks (starting from current week's Monday).

    Response:
        {
            "phases": [
                { "week_start": "YYYY-MM-DD", "phase": str, "is_current": bool }
            ],
            "current_phase": str | null,
            "current_phase_description": str | null
        }
    """

    permission_classes = [IsAuthenticated]

    PHASE_DESCRIPTIONS = {
        "carga": "Fase de construcción. Volumen alto, intensidad progresiva.",
        "descarga": "Semana de recuperación. Reducí volumen 30-40%.",
        "carrera": "Semana de competencia. Activaciones cortas, descansá.",
        "descanso": "Recuperación post-carrera. Actividad suave o descanso completo.",
        "lesion": "Recuperación de lesión. Seguí las indicaciones de tu coach.",
    }

    def get(self, request):
        _, org = _resolve_athlete_membership_view(request.user)

        athlete = Athlete.objects.filter(user=request.user, organization=org).first()
        if not athlete:
            return Response({"phases": [], "current_phase": None, "current_phase_description": None})

        try:
            weeks = int(request.query_params.get("weeks", 12))
        except (TypeError, ValueError):
            weeks = 12
        weeks = max(1, min(26, weeks))

        today = datetime.date.today()
        today_monday = today - datetime.timedelta(days=today.weekday())
        end_monday = today_monday + datetime.timedelta(weeks=weeks - 1)

        tws = {
            tw.week_start: tw.phase
            for tw in TrainingWeek.objects.filter(
                organization=org,
                athlete=athlete,
                week_start__gte=today_monday,
                week_start__lte=end_monday,
            )
        }

        phases = []
        for i in range(weeks):
            wk = today_monday + datetime.timedelta(weeks=i)
            phase = tws.get(wk)
            phases.append({
                "week_start": wk.isoformat(),
                "phase": phase,
                "is_current": i == 0,
            })

        current_phase = tws.get(today_monday)
        description = self.PHASE_DESCRIPTIONS.get(current_phase) if current_phase else None

        return Response({
            "phases": phases,
            "current_phase": current_phase,
            "current_phase_description": description,
        })


# ── Coach-side: athlete training phases for Calendar badge ────────────────────

class CoachAthleteTrainingPhasesView(OrgTenantMixin, APIView):
    """
    GET /api/p1/orgs/<org_id>/athletes/<athlete_id>/training-phases/
        ?from=YYYY-MM-DD&to=YYYY-MM-DD

    Returns training phases for a specific athlete within a date range.
    Used by the Calendar month-view to render phase badges per week.

    Response:
        { "phases": [{"week_start": "YYYY-MM-DD", "phase": str}] }

    403: not a coach/owner/athlete-self.
    404: athlete not found in org.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id: int, athlete_id: int):
        org = self.organization

        athlete = get_object_or_404(Athlete, pk=athlete_id, organization=org, is_active=True)

        # Athletes may only read their own phases
        if self.membership.role == "athlete":
            if not Athlete.objects.filter(pk=athlete_id, user=request.user, organization=org).exists():
                raise PermissionDenied("Athletes may only view their own phases.")

        # Parse date range; default to current month ± 1 week
        today = datetime.date.today()
        today_monday = today - datetime.timedelta(days=today.weekday())

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")

        try:
            from_date = datetime.date.fromisoformat(from_str) if from_str else today_monday - datetime.timedelta(weeks=2)
        except ValueError:
            from_date = today_monday - datetime.timedelta(weeks=2)

        try:
            to_date = datetime.date.fromisoformat(to_str) if to_str else today_monday + datetime.timedelta(weeks=6)
        except ValueError:
            to_date = today_monday + datetime.timedelta(weeks=6)

        # Snap to Monday
        from_monday = from_date - datetime.timedelta(days=from_date.weekday())
        to_monday = to_date - datetime.timedelta(days=to_date.weekday())

        tws = TrainingWeek.objects.filter(
            organization=org,
            athlete=athlete,
            week_start__gte=from_monday,
            week_start__lte=to_monday,
        ).values("week_start", "phase")

        return Response({
            "phases": [
                {"week_start": tw["week_start"].isoformat(), "phase": tw["phase"]}
                for tw in tws
            ]
        })
