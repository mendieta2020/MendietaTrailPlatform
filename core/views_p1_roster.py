"""
core/views_p1_roster.py

ViewSets for the P1 Roster API: Coach, Athlete (roster), Team,
Membership, and AthleteCoachAssignment.

Tenancy enforcement (Ley 1 — Non-Negotiable):
- resolve_membership(org_id) is called in initial() after authentication.
- get_queryset() always filters by self.organization — no exceptions.
- organization is NEVER derived from the request body; it comes from the URL.
- Athletes may read their own data; writes are role-gated per resource.

OrgTenantMixin contract:
- Subclasses call self.resolve_membership(org_id) to populate self.membership
  and self.organization.
- Fail-closed: no active membership → PermissionDenied 403.
"""

import datetime
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import services_assignment
from core.models import (
    Athlete,
    AthleteCoachAssignment,
    AthleteNotification,
    Coach,
    InternalMessage,
    Membership,
    Team,
    TeamInvitation,
    WorkoutAssignment,
)
from core.tenancy import get_active_membership

logger = logging.getLogger(__name__)
from core.serializers_p1_roster import (
    AthleteCoachAssignmentSerializer,
    AthleteRosterSerializer,
    CoachSerializer,
    MembershipSerializer,
    TeamInvitationCreateSerializer,
    TeamInvitationSerializer,
    TeamSerializer,
)
from core.tenancy import OrgTenantMixin

_WRITE_ROLES = {"owner", "coach"}


class CoachViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped Coach records.

    Read:
    - owner / coach / staff: list all coaches in the org.
    - athlete: list only coaches assigned to them via active AthleteCoachAssignment.

    Write:
    - owner: full CRUD, including create and soft-delete (is_active = False).
    - coach: PATCH their own record only (self-edit by user match).
    - athlete / staff: read-only.

    Destroy = soft-delete (is_active = False; record preserved for history).
    organization is derived from the URL org_id; never from the request body.
    """

    serializer_class = CoachSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return Coach.objects.none()
        qs = Coach.objects.filter(organization=self.organization).order_by("id")
        if self.membership.role == "athlete":
            # Athletes see only coaches they are assigned to (active assignments).
            assigned_coach_ids = AthleteCoachAssignment.objects.filter(
                athlete__user=self.request.user,
                organization=self.organization,
                ended_at__isnull=True,
            ).values_list("coach_id", flat=True)
            qs = qs.filter(pk__in=assigned_coach_ids)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def perform_create(self, serializer):
        if self.membership.role != "owner":
            raise PermissionDenied("Only owners can create coach records.")
        try:
            serializer.save(organization=self.organization)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        instance = serializer.instance
        if self.membership.role == "owner":
            serializer.save()
        elif self.membership.role == "coach":
            # Coaches may only edit their own profile.
            if instance.user != self.request.user:
                raise PermissionDenied("Coaches can only edit their own profile.")
            serializer.save()
        else:
            raise PermissionDenied("You do not have permission to update coach records.")

    def perform_destroy(self, instance):
        if self.membership.role != "owner":
            raise PermissionDenied("Only owners can deactivate coach records.")
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class AthleteRosterViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped Athlete records (roster view).

    Path: /api/p1/orgs/<org_id>/roster/athletes/
    The /roster/ segment avoids collision with the existing
    /api/p1/orgs/<org_id>/athletes/<athlete_id>/adherence/ endpoint.

    Read:
    - owner / coach: list all athletes.
    - athlete: list / retrieve own record only.

    Write:
    - owner / coach: create, update, soft-delete.
    - athlete: read-only.

    Destroy = soft-delete (is_active = False).
    organization is derived from the URL org_id; never from the request body.
    """

    serializer_class = AthleteRosterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return Athlete.objects.none()
        qs = Athlete.objects.filter(organization=self.organization).order_by("id")
        if self.membership.role == "athlete":
            qs = qs.filter(user=self.request.user)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify athlete records.")

    def perform_create(self, serializer):
        self._require_write_role()
        try:
            serializer.save(organization=self.organization)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        # PR-145d: athletes may PATCH their own location fields.
        # All other fields remain coach/owner-only.
        if self.membership.role == "athlete":
            _ATHLETE_ALLOWED_FIELDS = {"location_city", "location_lat", "location_lon"}
            disallowed = set(serializer.validated_data.keys()) - _ATHLETE_ALLOWED_FIELDS
            if disallowed:
                raise PermissionDenied(
                    f"Athletes may only update location fields. "
                    f"Disallowed fields: {', '.join(sorted(disallowed))}"
                )
        else:
            self._require_write_role()
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class TeamViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped Team records.

    Read: all roles.
    Write (create / update): owner / coach.
    Destroy (soft-delete): owner only.

    organization is derived from the URL org_id; never from the request body.
    """

    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return Team.objects.none()
        return Team.objects.filter(organization=self.organization).order_by("name")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def perform_create(self, serializer):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can create teams.")
        try:
            serializer.save(organization=self.organization)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can update teams.")
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_destroy(self, instance):
        if self.membership.role != "owner":
            raise PermissionDenied("Only owners can deactivate teams.")
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    # ── Team members CRUD (PR-145h) ──────────────────────────────────────────

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, *args, **kwargs):
        """
        GET  /api/p1/orgs/<org_id>/teams/<pk>/members/  — list athletes in team.
        POST /api/p1/orgs/<org_id>/teams/<pk>/members/  — add athlete to team.

        Athletes are managed via the Athlete.team FK (organization-scoped).
        Only coaches and owners can write. All roles can read.
        """
        team = get_object_or_404(Team, pk=self.kwargs["pk"], organization=self.organization)

        if request.method == "GET":
            athletes = Athlete.objects.filter(
                team=team, organization=self.organization, is_active=True
            ).select_related("user")
            data = [
                {
                    "athlete_id": a.pk,
                    "name": (a.user.get_full_name() or a.user.username),
                    "username": a.user.username,
                }
                for a in athletes
            ]
            return Response(data)

        # POST — add athlete to team
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can manage team members.")
        athlete_id = request.data.get("athlete_id")
        if not athlete_id:
            raise DRFValidationError({"athlete_id": "This field is required."})
        athlete = get_object_or_404(
            Athlete, pk=athlete_id, organization=self.organization, is_active=True
        )
        athlete.team = team
        athlete.save(update_fields=["team"])
        return Response(
            {"athlete_id": athlete.pk, "team_id": team.pk},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"members/(?P<athlete_id>\d+)",
    )
    def remove_member(self, request, athlete_id=None, *args, **kwargs):
        """
        DELETE /api/p1/orgs/<org_id>/teams/<pk>/members/<athlete_id>/

        Removes athlete from team by clearing Athlete.team FK.
        Only coaches and owners can remove members.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can manage team members.")
        team = get_object_or_404(Team, pk=self.kwargs["pk"], organization=self.organization)
        athlete = get_object_or_404(
            Athlete, pk=athlete_id, organization=self.organization
        )
        if athlete.team_id != team.pk:
            raise DRFValidationError({"detail": "Athlete is not a member of this team."})
        athlete.team = None
        athlete.save(update_fields=["team"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Compliance week (PR-145h / PR-148) ───────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="compliance-week")
    def compliance_week(self, request, *args, **kwargs):
        """
        GET /api/p1/orgs/<org_id>/teams/<pk>/compliance-week/?week=YYYY-MM-DD

        Returns a 7-day compliance grid (Mon→Sun) for every athlete in the team.
        week param = ISO date of any day in the desired week (defaults to today).

        PR-148 changes:
        - compliance_pct is now real (actual / planned ratio avg), not binary count.
        - sessions_per_day added: days with ≥2 non-canceled/skipped sessions.
        - compliance_color added at the athlete level (red/yellow/green/blue).

        Single bulk query: all assignments for team+week, grouped in Python.
        """
        team = get_object_or_404(Team, pk=self.kwargs["pk"], organization=self.organization)

        week_param = request.query_params.get("week")
        try:
            ref = datetime.date.fromisoformat(week_param) if week_param else datetime.date.today()
        except ValueError:
            raise DRFValidationError({"week": "Invalid date format. Use YYYY-MM-DD."})

        # Normalize to Monday of the week.
        week_start = ref - datetime.timedelta(days=ref.weekday())
        week_end = week_start + datetime.timedelta(days=6)
        week_days = [week_start + datetime.timedelta(days=i) for i in range(7)]

        athletes = list(
            Athlete.objects.filter(
                team=team, organization=self.organization, is_active=True
            ).select_related("user").order_by("user__last_name", "user__first_name")
        )
        athlete_ids = [a.pk for a in athletes]

        # Single bulk query: all assignments for these athletes in this week.
        assignments = list(
            WorkoutAssignment.objects.filter(
                organization=self.organization,
                athlete_id__in=athlete_ids,
                scheduled_date__gte=week_start,
                scheduled_date__lte=week_end,
            ).select_related("planned_workout", "athlete")
        )

        from collections import defaultdict, Counter  # noqa: PLC0415

        # For dot display: last assignment per (athlete, day) wins.
        by_athlete_date = defaultdict(dict)
        # All COMPLETED assignments per athlete (for real compliance_pct).
        completed_by_athlete = defaultdict(list)
        # Count of non-CANCELED/SKIPPED sessions per athlete per day.
        sessions_count_by_athlete = defaultdict(Counter)

        _EXCLUDED = {WorkoutAssignment.Status.CANCELED, WorkoutAssignment.Status.SKIPPED}

        for a in assignments:
            by_athlete_date[a.athlete_id][a.scheduled_date] = a
            if a.status == WorkoutAssignment.Status.COMPLETED:
                completed_by_athlete[a.athlete_id].append(a)
            if a.status not in _EXCLUDED:
                sessions_count_by_athlete[a.athlete_id][a.scheduled_date.isoformat()] += 1

        def _color(assignment):
            if assignment.status != WorkoutAssignment.Status.COMPLETED:
                return "gray"
            return assignment.compliance_color or "gray"

        def _day_entry(assignment):
            return {
                "color": _color(assignment),
                "assignment_id": assignment.pk,
                "workout_name": assignment.planned_workout.name if assignment.planned_workout else "",
            }

        def _assignment_compliance_pct(a):
            """Real compliance % for a single COMPLETED assignment."""
            if not a.actual_duration_seconds and not a.actual_distance_meters:
                return 100.0  # Completed manually without sync — trust the athlete
            pw = a.planned_workout
            ratios = []
            if pw and pw.estimated_duration_seconds and a.actual_duration_seconds:
                ratios.append(a.actual_duration_seconds / pw.estimated_duration_seconds)
            if pw and pw.estimated_distance_meters and a.actual_distance_meters:
                ratios.append(a.actual_distance_meters / pw.estimated_distance_meters)
            if not ratios:
                return 100.0
            return (sum(ratios) / len(ratios)) * 100

        def _week_compliance_color(pct):
            if pct < 70:
                return "red"
            if pct < 100:
                return "yellow"
            if pct < 120:
                return "green"
            return "blue"

        athletes_data = []
        for athlete in athletes:
            day_map = by_athlete_date.get(athlete.pk, {})
            all_completed = completed_by_athlete.get(athlete.pk, [])
            sessions_count = sessions_count_by_athlete.get(athlete.pk, Counter())

            days = {}
            overload_days = 0   # days where per-day compliance_color == "blue"
            consecutive_incomplete = 0
            max_consecutive = 0

            for day in week_days:
                assignment = day_map.get(day)
                if assignment is None:
                    days[day.isoformat()] = None
                else:
                    days[day.isoformat()] = _day_entry(assignment)
                    if assignment.status == WorkoutAssignment.Status.COMPLETED:
                        consecutive_incomplete = 0
                        if assignment.compliance_color == "blue":
                            overload_days += 1
                    elif assignment.status not in _EXCLUDED:
                        consecutive_incomplete += 1
                        max_consecutive = max(max_consecutive, consecutive_incomplete)

            # Real compliance_pct: mean of actual/planned ratios across all completed assignments.
            completed = len(all_completed)
            total = sum(sessions_count.values())
            pct_list = [_assignment_compliance_pct(a) for a in all_completed]
            compliance_pct = round(sum(pct_list) / len(pct_list)) if pct_list else 0
            compliance_color = _week_compliance_color(compliance_pct) if completed > 0 else "gray"

            # Multi-session indicator: days with ≥2 sessions this week.
            sessions_per_day = {date: cnt for date, cnt in sessions_count.items() if cnt >= 2}

            # Alert logic (priority: inactive > overload > praise > none)
            if max_consecutive >= 4:
                alert = "inactive_4d"
            elif overload_days >= 4:
                alert = "overload"
            elif compliance_pct >= 90 and completed >= 1:
                alert = "praise"
            else:
                alert = None

            athletes_data.append({
                "athlete_id": athlete.pk,
                "user_id": athlete.user_id,
                "athlete_name": (athlete.user.get_full_name() or athlete.user.username),
                "phone_number": athlete.phone_number or "",
                "days": days,
                "sessions_per_day": sessions_per_day,
                "compliance_color": compliance_color,
                "summary": {
                    "completed": completed,
                    "total": total,
                    "compliance_pct": compliance_pct,
                    "alert": alert,
                },
            })

        return Response({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "athletes": athletes_data,
        })


class MembershipViewSet(
    OrgTenantMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, retrieve, create, and update Membership within an organization.

    Destroy is intentionally not exposed — memberships are deactivated via
    PATCH is_active=False to preserve the access audit trail.

    Role rules:
    - owner: list all memberships, retrieve any, create, update any.
    - coach: list active memberships, retrieve any active; no write.
    - athlete: retrieve own membership only; no list, no write.

    Last-owner protection: the final active owner membership cannot be
    deactivated or have its role changed. This prevents an org from
    becoming permanently inaccessible.

    organization is derived from the URL org_id; never from the request body.
    """

    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return Membership.objects.none()
        qs = Membership.objects.filter(organization=self.organization).order_by("id")
        if self.membership.role == "athlete":
            qs = qs.filter(user=self.request.user)
        elif self.membership.role == "coach":
            qs = qs.filter(is_active=True)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def list(self, request, *args, **kwargs):
        if self.membership.role == "athlete":
            raise PermissionDenied("Athletes cannot list all memberships.")
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        if self.membership.role != "owner":
            raise PermissionDenied("Only owners can create memberships.")
        try:
            serializer.save(organization=self.organization)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        if self.membership.role != "owner":
            raise PermissionDenied("Only owners can modify memberships.")
        instance = serializer.instance
        new_role = serializer.validated_data.get("role", instance.role)
        new_is_active = serializer.validated_data.get("is_active", instance.is_active)

        # Last-owner protection: if this instance IS an owner, verify that
        # changing its role or deactivating it would not leave the org owner-less.
        if instance.role == "owner":
            losing_owner_status = (new_role != "owner") or (new_is_active is False)
            if losing_owner_status:
                active_owner_count = Membership.objects.filter(
                    organization=self.organization,
                    role="owner",
                    is_active=True,
                ).count()
                if active_owner_count <= 1:
                    raise DRFValidationError(
                        "Cannot remove or deactivate the last active owner of this organization."
                    )

        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)


class AthleteCoachAssignmentViewSet(
    OrgTenantMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, retrieve, create, and end AthleteCoachAssignment within an organization.

    No update, no delete — the only post-creation mutation is ending an assignment
    via the `end` action (sets ended_at; preserves history).

    Actions:
    - list     GET   /api/p1/orgs/<org_id>/coach-assignments/
    - create   POST  /api/p1/orgs/<org_id>/coach-assignments/
    - retrieve GET   /api/p1/orgs/<org_id>/coach-assignments/<pk>/
    - end      POST  /api/p1/orgs/<org_id>/coach-assignments/<pk>/end/

    create() delegates to services_assignment.assign_coach_to_athlete() — never
    creates AthleteCoachAssignment directly — so all business rules and tenancy
    cross-checks are enforced in the service layer.

    Roles: owner / coach only for all operations.
    organization is derived from the URL org_id; never from the request body.
    """

    serializer_class = AthleteCoachAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return AthleteCoachAssignment.objects.none()
        return AthleteCoachAssignment.objects.filter(organization=self.organization).order_by("-assigned_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can manage coach assignments.")

    def create(self, request, *args, **kwargs):
        """
        Create an AthleteCoachAssignment via the service layer.

        Delegates to services_assignment.assign_coach_to_athlete() instead of
        calling serializer.save() directly, so all business-rule validations
        (duplicate primary guard, org-ownership cross-checks) are enforced.
        """
        self._require_write_role()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        athlete = serializer.validated_data["athlete"]
        coach = serializer.validated_data["coach"]
        role = serializer.validated_data["role"]
        try:
            assignment = services_assignment.assign_coach_to_athlete(
                athlete=athlete,
                coach=coach,
                organization=self.organization,
                role=role,
                assigned_by=request.user,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)
        out = AthleteCoachAssignmentSerializer(
            assignment, context=self.get_serializer_context()
        )
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="end")
    def end(self, request, org_id=None, pk=None):
        """
        End an active AthleteCoachAssignment.

        Sets ended_at = now via services_assignment.end_coach_assignment().
        Returns 400 if the assignment has already ended.
        Roles: owner / coach.
        """
        self._require_write_role()
        assignment = self.get_object()
        try:
            updated = services_assignment.end_coach_assignment(assignment=assignment)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)
        return Response(
            AthleteCoachAssignmentSerializer(
                updated, context=self.get_serializer_context()
            ).data
        )


_NOTIFY_ALLOWED_ROLES = {"owner", "coach"}


class CoachNotifyAthleteDeviceView(APIView):
    """
    POST /api/coach/roster/<int:membership_id>/notify-device/

    Creates a 'device_connect' notification for the target athlete.

    Security contract:
    - Caller must be owner or coach in at least one active organization.
    - membership_id must belong to that same organization and have role='athlete'.
    - Duplicate guard: if an unread 'device_connect' notification already exists
      for this recipient+org, no new record is created (returns created:false).

    Response:
        {"ok": true, "created": bool}

    403: caller lacks an active owner/coach membership.
    404: target membership not found or belongs to a different org.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, membership_id):
        # --- Resolve caller's org (fail-closed) ---
        coach_membership = (
            Membership.objects.select_related("organization")
            .filter(
                user=request.user,
                is_active=True,
                role__in=list(_NOTIFY_ALLOWED_ROLES),
            )
            .first()
        )
        if coach_membership is None:
            raise PermissionDenied("Only coaches and owners can send device notifications.")

        org = coach_membership.organization

        # --- Resolve target membership (fail-closed — re-verify org) ---
        try:
            target = Membership.objects.select_related("user").get(
                pk=membership_id,
                organization=org,
                role=Membership.Role.ATHLETE,
                is_active=True,
            )
        except Membership.DoesNotExist:
            raise NotFound("Athlete membership not found in this organization.")

        # --- Duplicate guard: no double-unread notification of same type ---
        already_exists = AthleteNotification.objects.filter(
            organization=org,
            recipient=target.user,
            notification_type="device_connect",
            read=False,
        ).exists()

        created = False
        if not already_exists:
            AthleteNotification.objects.create(
                organization=org,
                recipient=target.user,
                sender=request.user,
                notification_type="device_connect",
            )
            created = True

        logger.info(
            "coach_athlete_device_notification_sent",
            extra={
                "event": "coach_athlete_device_notification_sent",
                "organization_id": org.id,
                "coach_user_id": request.user.id,
                "athlete_membership_id": membership_id,
                "created": created,
                "outcome": "ok",
            },
        )
        return Response({"ok": True, "created": created})


class CoachBriefingView(OrgTenantMixin, APIView):
    """
    GET /api/p1/orgs/<org_id>/coach-briefing/

    Morning briefing for coaches and owners: yesterday's training summary,
    overloaded and inactive athletes, and unread message count.

    PR-148: All queries are bulk (no loops). Organization-scoped (fail-closed).
    Roles: coach, owner only.
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id):
        if self.membership.role not in {"owner", "coach"}:
            raise PermissionDenied("Only coaches and owners can access the briefing.")

        org = self.organization
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        week_start = today - datetime.timedelta(days=today.weekday())
        four_days_ago = today - datetime.timedelta(days=4)

        # Total athletes in org visible to the coach (same set as Plantilla roster).
        athletes_total = Membership.objects.filter(
            organization=org,
            role=Membership.Role.ATHLETE,
            is_active=True,
        ).count()

        # Athletes who completed at least 1 assignment yesterday.
        athletes_trained_yesterday = (
            WorkoutAssignment.objects.filter(
                organization=org,
                scheduled_date=yesterday,
                status=WorkoutAssignment.Status.COMPLETED,
            )
            .values("athlete_id")
            .distinct()
            .count()
        )

        # Athletes with at least 1 blue (≥120% effort) assignment this week.
        athletes_overloaded = (
            WorkoutAssignment.objects.filter(
                organization=org,
                scheduled_date__range=(week_start, today),
                status=WorkoutAssignment.Status.COMPLETED,
                compliance_color="blue",
            )
            .values("athlete_id")
            .distinct()
            .count()
        )

        # Athletes with no COMPLETED assignment in the last 4 days.
        active_4d_ids = set(
            WorkoutAssignment.objects.filter(
                organization=org,
                scheduled_date__range=(four_days_ago, today),
                status=WorkoutAssignment.Status.COMPLETED,
            )
            .values_list("athlete_id", flat=True)
            .distinct()
        )
        all_athlete_ids = set(
            Athlete.objects.filter(organization=org, is_active=True).values_list("pk", flat=True)
        )
        athletes_inactive_4d = len(all_athlete_ids - active_4d_ids)

        # Unread InternalMessages addressed to the requesting user in this org.
        unread_messages = InternalMessage.objects.filter(
            organization=org,
            recipient=request.user,
            read_at__isnull=True,
        ).count()

        logger.info(
            "coach_briefing_fetched",
            extra={
                "event": "coach_briefing_fetched",
                "organization_id": org.id,
                "user_id": request.user.id,
                "outcome": "ok",
            },
        )
        return Response({
            "yesterday_date": yesterday.isoformat(),
            "athletes_trained_yesterday": athletes_trained_yesterday,
            "athletes_total": athletes_total,
            "athletes_overloaded": athletes_overloaded,
            "athletes_inactive_4d": athletes_inactive_4d,
            "unread_messages": unread_messages,
        })


# ==============================================================================
# PR-165a: TeamInvitationViewSet
# ==============================================================================

class TeamInvitationViewSet(OrgTenantMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    GET    /api/p1/orgs/{org_id}/invitations/team/       — list (owner/coach)
    POST   /api/p1/orgs/{org_id}/invitations/team/       — create (owner only)
    DELETE /api/p1/orgs/{org_id}/invitations/team/{pk}/  — revoke pending (owner only)
    """

    _OWNER_ROLES = {"owner"}
    _LIST_ROLES  = {"owner", "coach"}  # coaches can see but not create

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(kwargs["org_id"])

    def get_queryset(self):
        return TeamInvitation.objects.filter(organization=self.organization)

    def get_serializer_class(self):
        if self.action == "create":
            return TeamInvitationCreateSerializer
        return TeamInvitationSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.organization
        return ctx

    def list(self, request, *args, **kwargs):
        if self.membership.role not in self._LIST_ROLES:
            raise PermissionDenied("Solo el owner o coach puede ver las invitaciones.")
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if self.membership.role not in self._OWNER_ROLES:
            raise PermissionDenied("Solo el owner puede crear invitaciones de equipo.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save()

        frontend_url = getattr(__import__("django.conf", fromlist=["settings"]).settings, "FRONTEND_URL", "https://app.quantoryn.com")
        join_url = f"{frontend_url}/join/team/{invitation.token}"

        logger.info(
            "team_invitation_created",
            extra={
                "organization_id": self.organization.id,
                "user_id": request.user.id,
                "role": invitation.role,
                "invitation_token": str(invitation.token),
            },
        )

        read_data = TeamInvitationSerializer(invitation, context=self.get_serializer_context()).data
        read_data["join_url"] = join_url
        return Response(read_data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        if self.membership.role not in self._OWNER_ROLES:
            raise PermissionDenied("Solo el owner puede revocar invitaciones.")

        invitation = self.get_object()
        if invitation.status != TeamInvitation.Status.PENDING:
            return Response(
                {"detail": "Solo se pueden eliminar invitaciones pendientes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "team_invitation_revoked",
            extra={
                "organization_id": self.organization.id,
                "user_id": request.user.id,
                "invitation_token": str(invitation.token),
            },
        )
        invitation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# PR-165a Fix 2: TeamMembersView — list non-athlete memberships
# ==============================================================================

_TEAM_ROLES = {"owner", "coach", "staff"}
_TEAM_ADMIN_ROLES = {"owner", "admin"}


class TeamMembersView(APIView):
    """
    GET /api/p1/orgs/{org_id}/team-members/
    Returns all non-athlete memberships (owner, coach, staff) for the org.
    Restricted to owner/admin role.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, org_id):
        # Fail-closed tenancy: caller must be owner or admin of the org
        caller = Membership.objects.filter(
            user=request.user,
            organization_id=org_id,
            role__in=list(_TEAM_ADMIN_ROLES),
            is_active=True,
        ).first()
        if not caller:
            return Response(
                {"detail": "No tienes permiso para ver los miembros del equipo."},
                status=status.HTTP_403_FORBIDDEN,
            )

        members = (
            Membership.objects
            .filter(organization_id=org_id, role__in=list(_TEAM_ROLES), is_active=True)
            .select_related("user")
            .order_by("role", "user__first_name")
        )

        data = []
        for m in members:
            name = (
                f"{m.user.first_name} {m.user.last_name}".strip()
                or m.user.username
                or m.user.email
            )
            data.append({
                "id": m.id,
                "user_id": m.user_id,
                "name": name,
                "email": m.user.email,
                "role": m.role,
                "joined_at": m.joined_at,
            })

        return Response(data)
