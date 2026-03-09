"""
core/views_p1.py

ViewSets for the P1 organization-first domain: RaceEvent and AthleteGoal.

Tenancy enforcement:
- resolve_membership(org_id) is called in initial() after authentication.
- get_queryset() always filters by self.organization.
- organization is never derived from request body — it comes from the URL.
- Write operations (create/update/destroy) require role in {owner, coach}.
- Athletes may read; they may not write.
- For AthleteGoal, athletes may only read their own goals.

OrgTenantMixin contract:
- Subclasses call self.resolve_membership(org_id) to populate self.membership
  and self.organization.
- org_id comes from self.kwargs["org_id"] (URL path parameter).
"""

from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from core.models import AthleteGoal, RaceEvent
from core.serializers_p1 import AthleteGoalSerializer, RaceEventSerializer
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
