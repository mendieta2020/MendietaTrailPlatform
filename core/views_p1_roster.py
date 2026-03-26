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

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import services_assignment
from core.models import (
    Athlete,
    AthleteCoachAssignment,
    AthleteNotification,
    Coach,
    Membership,
    Team,
)
from core.tenancy import get_active_membership

logger = logging.getLogger(__name__)
from core.serializers_p1_roster import (
    AthleteCoachAssignmentSerializer,
    AthleteRosterSerializer,
    CoachSerializer,
    MembershipSerializer,
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
