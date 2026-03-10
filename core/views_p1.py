"""
core/views_p1.py

ViewSets for the P1 organization-first domain: RaceEvent, AthleteGoal,
AthleteProfile, and WorkoutAssignment.

Tenancy enforcement:
- resolve_membership(org_id) is called in initial() after authentication.
- get_queryset() always filters by self.organization.
- organization is never derived from request body — it comes from the URL.
- Write operations require role in {owner, coach} unless athletes are explicitly
  permitted (AthleteProfile: athletes may update their own;
  WorkoutAssignment: athletes may update athlete_notes + athlete_moved_date on own).
- Athletes may read; write is role-gated per resource.

OrgTenantMixin contract:
- Subclasses call self.resolve_membership(org_id) to populate self.membership
  and self.organization.
- org_id comes from self.kwargs["org_id"] (URL path parameter).
"""

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError

from core.models import AthleteGoal, AthleteProfile, RaceEvent, WorkoutAssignment
from core.serializers_p1 import (
    AthleteGoalSerializer,
    AthleteProfileSerializer,
    RaceEventSerializer,
    WorkoutAssignmentAthleteSerializer,
    WorkoutAssignmentSerializer,
)
from core.tenancy import OrgTenantMixin

_WRITE_ROLES = {"owner", "coach"}


class RaceEventViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped RaceEvent catalog.

    All roles can read. Only owner/coach can write.
    """

    serializer_class = RaceEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return RaceEvent.objects.none()
        return RaceEvent.objects.filter(organization=self.organization)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify race events.")

    def perform_create(self, serializer):
        self._require_write_role()
        serializer.save(
            organization=self.organization,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        self._require_write_role()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()


class AthleteGoalViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped AthleteGoal records.

    Coaches can read all goals in the org and write any.
    Athletes can only read their own goals; they cannot write.
    """

    serializer_class = AthleteGoalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return AthleteGoal.objects.none()
        qs = AthleteGoal.objects.filter(organization=self.organization)
        if self.membership.role == "athlete":
            qs = qs.filter(athlete__user=self.request.user)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify athlete goals.")

    def perform_create(self, serializer):
        self._require_write_role()
        serializer.save(
            organization=self.organization,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        self._require_write_role()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()


class AthleteProfileViewSet(
    OrgTenantMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Retrieve, list, create, and update AthleteProfile within an organization.

    Destroy is intentionally not exposed — profile deletion is a high-risk,
    out-of-scope operation for this PR.

    Lookup field is athlete_id (the OneToOne FK column) so callers can address
    profiles by athlete PK rather than the opaque profile PK.

    Role rules:
    - coach/owner: list all, retrieve any, create, update any.
    - athlete: cannot list; retrieve and update own profile only; cannot create.
    """

    serializer_class = AthleteProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "athlete_id"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return AthleteProfile.objects.none()
        qs = AthleteProfile.objects.filter(organization=self.organization).order_by("athlete_id")
        if self.membership.role == "athlete":
            qs = qs.filter(athlete__user=self.request.user)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def list(self, request, *args, **kwargs):
        if self.membership.role == "athlete":
            raise PermissionDenied("Athletes cannot list all profiles.")
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can create athlete profiles.")
        try:
            serializer.save(
                organization=self.organization,
                updated_by=self.request.user,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        # Athletes may update their own profile (queryset already restricts to own).
        # No additional role check needed — the queryset gate is sufficient.
        try:
            serializer.save(updated_by=self.request.user)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)


# ==============================================================================
# PR-117: WorkoutAssignment ViewSet
# ==============================================================================


class WorkoutAssignmentViewSet(
    OrgTenantMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, retrieve, create, and update WorkoutAssignment within an organization.

    Destroy is intentionally not exposed — use status="canceled" to retire
    an assignment and preserve the audit trail.

    Role rules:
    - coach/owner: list all, retrieve any, create, update any (all fields per matrix).
    - athlete: list own only, retrieve own only, partial_update own (athlete_notes +
      athlete_moved_date only; all other fields are read-only in the athlete serializer).
      Athletes cannot create assignments.

    Serializer dispatch:
    - coach/owner/admin → WorkoutAssignmentSerializer (full write surface).
    - athlete           → WorkoutAssignmentAthleteSerializer (restricted write surface).

    Tenancy: organization derived from URL org_id, never from request body.
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return WorkoutAssignment.objects.none()
        qs = WorkoutAssignment.objects.filter(organization=self.organization)
        if self.membership.role == "athlete":
            qs = qs.filter(athlete__user=self.request.user)
        return qs

    def get_serializer_class(self):
        if getattr(self, "membership", None) and self.membership.role == "athlete":
            return WorkoutAssignmentAthleteSerializer
        return WorkoutAssignmentSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def perform_create(self, serializer):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can create workout assignments.")
        planned_workout = serializer.validated_data["planned_workout"]
        try:
            serializer.save(
                organization=self.organization,
                assigned_by=self.request.user,
                snapshot_version=planned_workout.structure_version,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        # Athletes can update their own (queryset already restricts to own).
        # The athlete serializer enforces write-only on athlete_notes + athlete_moved_date.
        # Coaches can update any assignment in the org.
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)
