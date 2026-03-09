"""
core/views_p1.py

ViewSets for the P1 organization-first domain: RaceEvent, AthleteGoal,
and AthleteProfile.

Tenancy enforcement:
- resolve_membership(org_id) is called in initial() after authentication.
- get_queryset() always filters by self.organization.
- organization is never derived from request body — it comes from the URL.
- Write operations require role in {owner, coach} unless athletes are explicitly
  permitted (AthleteProfile: athletes may update their own).
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

from core.models import AthleteGoal, AthleteProfile, RaceEvent
from core.serializers_p1 import (
    AthleteGoalSerializer,
    AthleteProfileSerializer,
    RaceEventSerializer,
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
