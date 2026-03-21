"""
core/views_p1.py

ViewSets for the P1 organization-first domain: RaceEvent, AthleteGoal,
AthleteProfile, WorkoutAssignment, and WorkoutReconciliation.

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

import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import mixins, permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core import services_reconciliation
from core.models import (
    Alumno,
    Athlete,
    AthleteGoal,
    AthleteProfile,
    CompletedActivity,
    ExternalIdentity,
    OAuthCredential,
    PlannedWorkout,
    RaceEvent,
    Team,
    WorkoutAssignment,
    WorkoutBlock,
    WorkoutDeliveryRecord,
    WorkoutInterval,
    WorkoutLibrary,
    WorkoutReconciliation,
)
from core.serializers_p1 import (
    AthleteGoalSerializer,
    AthleteProfileSerializer,
    ExternalIdentitySerializer,
    PlannedWorkoutReadSerializer,
    PlannedWorkoutWriteSerializer,
    RaceEventSerializer,
    WorkoutAssignmentAthleteSerializer,
    WorkoutAssignmentSerializer,
    WorkoutBlockReadSerializer,
    WorkoutBlockSerializer,
    WorkoutIntervalSerializer,
    WorkoutLibrarySerializer,
    WorkoutReconciliationSerializer,
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
        qs = WorkoutAssignment.objects.filter(
            organization=self.organization
        ).select_related("planned_workout")
        if self.membership.role == "athlete":
            qs = qs.filter(athlete__user=self.request.user)
        else:
            # Coach/owner only: optional athlete_id filter.
            athlete_id = self.request.query_params.get("athlete_id")
            if athlete_id:
                try:
                    qs = qs.filter(athlete_id=int(athlete_id))
                except (ValueError, TypeError):
                    raise DRFValidationError(
                        {"athlete_id": "Must be a positive integer."}
                    )

            # Optional team_id filter: scopes to athletes in a specific team.
            team_id = self.request.query_params.get("team_id")
            if team_id:
                try:
                    qs = qs.filter(athlete__team_id=int(team_id))
                except (ValueError, TypeError):
                    raise DRFValidationError(
                        {"team_id": "Must be a positive integer."}
                    )

        # Date range filters apply to both roles.
        date_from = self.request.query_params.get("date_from")
        if date_from:
            try:
                qs = qs.filter(
                    scheduled_date__gte=datetime.date.fromisoformat(date_from)
                )
            except ValueError:
                raise DRFValidationError(
                    {"date_from": "Invalid date format. Use YYYY-MM-DD."}
                )
        date_to = self.request.query_params.get("date_to")
        if date_to:
            try:
                qs = qs.filter(
                    scheduled_date__lte=datetime.date.fromisoformat(date_to)
                )
            except ValueError:
                raise DRFValidationError(
                    {"date_to": "Invalid date format. Use YYYY-MM-DD."}
                )
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

    @action(detail=True, methods=["post"], url_path="push")
    def push(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/<pk>/push/

        Enqueue a SuuntoPlus Guide push so the PlannedWorkout appears on the
        athlete's Suunto watch.

        Requires coach or owner role. Returns 202 Accepted when the Celery
        task is enqueued. The task is idempotent: a second push on an already-
        sent assignment is a noop.
        """
        from core.provider_capabilities import CAP_OUTBOUND_WORKOUTS, provider_supports

        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can push workouts.")

        assignment = get_object_or_404(
            WorkoutAssignment,
            pk=self.kwargs["pk"],
            organization=self.organization,
        )

        provider = "suunto"

        if not provider_supports(provider, CAP_OUTBOUND_WORKOUTS):
            return Response(
                {"detail": "provider_no_outbound", "provider": provider},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bridge Athlete → Alumno → OAuthCredential
        # Alumno.usuario is a OneToOneField to User (related_name='perfil_alumno').
        alumno = getattr(assignment.athlete.user, "perfil_alumno", None)
        if alumno is None:
            return Response(
                {"detail": "no_suunto_credential"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not OAuthCredential.objects.filter(alumno=alumno, provider=provider).exists():
            return Response(
                {"detail": "no_suunto_credential"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lazy import: Law 4 — integrations/ must not be imported at module level in core/
        from integrations.suunto.tasks_guides import push_guide  # noqa: PLC0415

        push_guide.delay(
            assignment_id=assignment.pk,
            organization_id=self.organization.pk,
            alumno_id=alumno.pk,
        )

        return Response(
            {"status": "queued", "assignment_id": assignment.pk},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="bulk-assign-team")
    def bulk_assign_team(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/bulk-assign-team/

        Assigns a PlannedWorkout to every active Athlete in a Team on a given date.
        Requires coach or owner role.

        Request body:
          {
            "planned_workout_id": <int>,
            "team_id": <int>,
            "scheduled_date": "YYYY-MM-DD",
            "coach_notes": "" (optional)
          }

        Returns:
          { "created": <int>, "assignments": [...] }
        """
        from core.services_workout import bulk_assign_team_workout  # noqa: PLC0415

        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can bulk-assign workouts.")

        planned_workout_id = request.data.get("planned_workout_id")
        team_id = request.data.get("team_id")
        scheduled_date_raw = request.data.get("scheduled_date")
        coach_notes = request.data.get("coach_notes", "")

        errors = {}
        if not planned_workout_id:
            errors["planned_workout_id"] = "This field is required."
        if not team_id:
            errors["team_id"] = "This field is required."
        if not scheduled_date_raw:
            errors["scheduled_date"] = "This field is required."
        if errors:
            raise DRFValidationError(errors)

        try:
            scheduled_date = datetime.date.fromisoformat(str(scheduled_date_raw))
        except ValueError:
            raise DRFValidationError(
                {"scheduled_date": "Invalid date format. Use YYYY-MM-DD."}
            )

        planned_workout = get_object_or_404(
            PlannedWorkout,
            pk=planned_workout_id,
            organization=self.organization,
        )
        team = get_object_or_404(
            Team,
            pk=team_id,
            organization=self.organization,
        )

        try:
            assignments = bulk_assign_team_workout(
                planned_workout=planned_workout,
                team=team,
                organization=self.organization,
                scheduled_date=scheduled_date,
                assigned_by=request.user,
                coach_notes=coach_notes,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

        serializer = WorkoutAssignmentSerializer(
            assignments, many=True, context=self.get_serializer_context()
        )
        return Response(
            {"created": len(assignments), "assignments": serializer.data},
            status=status.HTTP_201_CREATED,
        )


# ==============================================================================
# PR-119: Reconciliation ViewSet
# ==============================================================================


class ReconciliationViewSet(OrgTenantMixin, viewsets.GenericViewSet):
    """
    Reconciliation endpoints nested under a WorkoutAssignment.

    URL prefix: /api/p1/orgs/<org_id>/assignments/<assignment_id>/reconciliation/

    Actions:
    - retrieve  (GET)   — read reconciliation state; coach sees any, athlete sees own.
    - reconcile (POST)  — coach-only; trigger auto or manual reconciliation.
    - miss      (POST)  — coach-only; mark assignment as missed.

    Plan ≠ Real invariant: these endpoints never modify PlannedWorkout or
    CompletedActivity. All mutations go through services_reconciliation.

    Tenancy: organization derived from URL org_id, never from request body.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkoutReconciliationSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def _get_assignment(self):
        """
        Resolve the assignment from the URL, scoped to self.organization.
        Athletes can only resolve their own assignments (fail-closed 404).
        """
        qs = WorkoutAssignment.objects.filter(
            pk=self.kwargs["assignment_id"],
            organization=self.organization,
        )
        if self.membership.role == "athlete":
            qs = qs.filter(athlete__user=self.request.user)
        try:
            return qs.get()
        except WorkoutAssignment.DoesNotExist:
            raise NotFound("Assignment not found.")

    def retrieve(self, request, *args, **kwargs):
        assignment = self._get_assignment()
        try:
            rec = assignment.reconciliation
        except WorkoutReconciliation.DoesNotExist:
            raise NotFound("No reconciliation record for this assignment.")
        return Response(WorkoutReconciliationSerializer(rec).data)

    def reconcile(self, request, *args, **kwargs):
        """
        Trigger reconciliation for an assignment.

        Body (optional):
          completed_activity_id: int  — explicit match; omit to run auto-match.
          notes: str                  — coach notes stored on the record.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can trigger reconciliation.")
        assignment = self._get_assignment()
        activity_id = request.data.get("completed_activity_id")
        notes = request.data.get("notes", "")
        if activity_id:
            try:
                activity = CompletedActivity.objects.get(
                    pk=activity_id,
                    athlete__organization=self.organization,
                )
            except CompletedActivity.DoesNotExist:
                raise NotFound("Activity not found.")
            rec = services_reconciliation.reconcile(
                assignment=assignment,
                activity=activity,
                notes=notes,
            )
        else:
            rec = services_reconciliation.auto_match_and_reconcile(assignment=assignment)
        return Response(WorkoutReconciliationSerializer(rec).data)

    def miss(self, request, *args, **kwargs):
        """Mark the assignment as MISSED. Coach-only."""
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can mark assignments missed.")
        assignment = self._get_assignment()
        notes = request.data.get("notes", "")
        rec = services_reconciliation.mark_assignment_missed(
            assignment=assignment, notes=notes
        )
        return Response(WorkoutReconciliationSerializer(rec).data)


# ==============================================================================
# PR-119: Athlete Weekly Adherence ViewSet
# ==============================================================================


# ==============================================================================
# PR-128: WorkoutLibrary + PlannedWorkout ViewSets
# ==============================================================================


class WorkoutLibraryViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for organization-scoped WorkoutLibrary.

    coach/owner: full CRUD.
    athlete: read-only, public libraries only (is_public=True).

    organization is derived from URL org_id; never from the request body.
    """

    serializer_class = WorkoutLibrarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return WorkoutLibrary.objects.none()
        qs = WorkoutLibrary.objects.filter(organization=self.organization)
        if self.membership.role == "athlete":
            qs = qs.filter(is_public=True)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify workout libraries.")

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


class PlannedWorkoutViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for PlannedWorkout records nested under a WorkoutLibrary.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/

    Tenancy: organization and library are derived from the URL only.
    Library ownership is validated in initial() — fail-closed 404 if the
    library does not belong to self.organization, or if an athlete attempts
    to access a private library.

    Serializer dispatch:
    - GET  → PlannedWorkoutReadSerializer (includes nested blocks + intervals)
    - write → PlannedWorkoutWriteSerializer (flat; library injected from URL)

    coach/owner: full CRUD.
    athlete: read-only, public libraries only.
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])
        # Validate library belongs to this org — fail-closed (never reveal existence).
        library_qs = WorkoutLibrary.objects.filter(
            pk=self.kwargs["library_id"],
            organization=self.organization,
        )
        if self.membership.role == "athlete":
            library_qs = library_qs.filter(is_public=True)
        if not library_qs.exists():
            raise NotFound("Library not found.")

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return PlannedWorkout.objects.none()
        qs = PlannedWorkout.objects.filter(
            organization=self.organization,
            library_id=self.kwargs["library_id"],
        )
        if self.membership.role == "athlete":
            qs = qs.filter(library__is_public=True)
        return qs

    def get_serializer_class(self):
        if self.request.method == "GET":
            return PlannedWorkoutReadSerializer
        return PlannedWorkoutWriteSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify planned workouts.")

    def perform_create(self, serializer):
        self._require_write_role()
        try:
            serializer.save(
                organization=self.organization,
                library_id=self.kwargs["library_id"],
                created_by=self.request.user,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        self._require_write_role()
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()


class WorkoutBlockViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for WorkoutBlock records nested under a PlannedWorkout.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/blocks/

    Tenancy: org, library, and workout are all validated in initial() — fail-closed
    404 if any ancestor does not belong to self.organization.

    Serializer dispatch:
    - GET  → WorkoutBlockReadSerializer (includes nested intervals)
    - write → WorkoutBlockSerializer (flat)

    coach/owner: full CRUD.
    athlete: read-only.
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])
        if not WorkoutLibrary.objects.filter(
            pk=self.kwargs["library_id"], organization=self.organization
        ).exists():
            raise NotFound("Library not found.")
        if not PlannedWorkout.objects.filter(
            pk=self.kwargs["workout_id"],
            organization=self.organization,
            library_id=self.kwargs["library_id"],
        ).exists():
            raise NotFound("Workout not found.")

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return WorkoutBlock.objects.none()
        return WorkoutBlock.objects.filter(
            organization=self.organization,
            planned_workout_id=self.kwargs["workout_id"],
            planned_workout__library_id=self.kwargs["library_id"],
        )

    def get_serializer_class(self):
        if self.request.method == "GET":
            return WorkoutBlockReadSerializer
        return WorkoutBlockSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify workout blocks.")

    def perform_create(self, serializer):
        self._require_write_role()
        try:
            serializer.save(
                organization=self.organization,
                planned_workout_id=self.kwargs["workout_id"],
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        self._require_write_role()
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()


class WorkoutIntervalViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for WorkoutInterval records nested under a WorkoutBlock.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/blocks/<block_id>/intervals/

    Tenancy: the full parent chain (library → workout → block) is validated in
    initial() — fail-closed 404 if any ancestor does not belong to self.organization.

    coach/owner: full CRUD.
    athlete: read-only.
    """

    serializer_class = WorkoutIntervalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])
        if not WorkoutLibrary.objects.filter(
            pk=self.kwargs["library_id"], organization=self.organization
        ).exists():
            raise NotFound("Library not found.")
        if not PlannedWorkout.objects.filter(
            pk=self.kwargs["workout_id"],
            organization=self.organization,
            library_id=self.kwargs["library_id"],
        ).exists():
            raise NotFound("Workout not found.")
        if not WorkoutBlock.objects.filter(
            pk=self.kwargs["block_id"],
            organization=self.organization,
            planned_workout_id=self.kwargs["workout_id"],
        ).exists():
            raise NotFound("Block not found.")

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return WorkoutInterval.objects.none()
        return WorkoutInterval.objects.filter(
            organization=self.organization,
            block_id=self.kwargs["block_id"],
            block__planned_workout_id=self.kwargs["workout_id"],
            block__planned_workout__library_id=self.kwargs["library_id"],
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can modify workout intervals.")

    def perform_create(self, serializer):
        self._require_write_role()
        try:
            serializer.save(
                organization=self.organization,
                block_id=self.kwargs["block_id"],
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        self._require_write_role()
        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()


class AthleteAdherenceViewSet(OrgTenantMixin, viewsets.GenericViewSet):
    """
    Weekly adherence aggregation for one athlete.

    URL: /api/p1/orgs/<org_id>/athletes/<athlete_id>/adherence/
    Query params:
      week_start: YYYY-MM-DD (required) — Monday of the target week.

    Role rules:
    - coach/owner: can query any athlete in the org.
    - athlete:     can only query their own adherence (fail-closed 404 otherwise).
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def retrieve(self, request, *args, **kwargs):
        athlete_id = self.kwargs["athlete_id"]
        qs = Athlete.objects.filter(pk=athlete_id, organization=self.organization)
        if self.membership.role == "athlete":
            qs = qs.filter(user=self.request.user)
        try:
            athlete = qs.get()
        except Athlete.DoesNotExist:
            raise NotFound("Athlete not found.")

        week_start_str = request.query_params.get("week_start")
        if not week_start_str:
            raise DRFValidationError({"week_start": "Required query parameter."})
        try:
            week_start = datetime.date.fromisoformat(week_start_str)
        except ValueError:
            raise DRFValidationError({"week_start": "Invalid date format. Use YYYY-MM-DD."})

        result = services_reconciliation.compute_weekly_adherence(
            organization=self.organization,
            athlete=athlete,
            week_start=week_start,
        )
        return Response({
            "week_start": result.week_start.isoformat(),
            "week_end": result.week_end.isoformat(),
            "organization_id": result.organization_id,
            "athlete_id": result.athlete_id,
            "planned_count": result.planned_count,
            "reconciled_count": result.reconciled_count,
            "missed_count": result.missed_count,
            "unmatched_count": result.unmatched_count,
            "avg_compliance_score": result.avg_compliance_score,
            "adherence_pct": round(result.adherence_pct, 1),
        })


# ==============================================================================
# PR-149: Dashboard Analytics View (P2)
# URL: /api/p1/orgs/<org_id>/dashboard-analytics/
# Read-only. Owner/coach only.
# ==============================================================================


class DashboardAnalyticsView(OrgTenantMixin, views.APIView):
    """
    Read-only analytics summary for the coach dashboard.

    Returns:
      - active_athletes_count: total Athlete rows in the org
      - pmc_series: [{date, ctl, atl, tsb}, ...] — 90 trailing days
        computed from WorkoutAssignment → planned_workout → planned_tss

    Plan ≠ Real invariant: only planning-side TSS is used.
    CompletedActivity execution data is never read here.

    Role gate: owner/coach only. Athletes may not access org-level analytics.
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id: int):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Analytics are only available to coaches and owners.")

        from core import services_analytics

        data = services_analytics.compute_org_pmc(organization=self.organization)
        return Response(data)


# ==============================================================================
# PR-128: Real-side PMC — CTL/ATL/TSB from CompletedActivity
# ==============================================================================


class AthleteRealPMCView(OrgTenantMixin, views.APIView):
    """
    Real-side PMC (CTL/ATL/TSB) for a single athlete, derived from CompletedActivity.

    Plan ≠ Real invariant: only CompletedActivity execution data is read here.
    PlannedWorkout and WorkoutAssignment are never accessed.

    Role gate:
    - owner / coach: may retrieve any athlete's PMC within their org.
    - athlete: may only retrieve their own PMC (404 if accessing another athlete).

    URL: GET /api/p1/orgs/<org_id>/athletes/<athlete_id>/pmc/real/
    Query params:
      - days (int, optional): trailing window in days, default 90, max 365.

    Returns:
      {
        "athlete_id": int,
        "organization_id": int,
        "days": int,
        "data": [{"date", "tss", "ctl", "atl", "tsb"}, ...]
      }
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get(self, request, org_id: int, athlete_id: int):
        # Resolve athlete — 404 if not found or not in this org (fail-closed)
        athlete = get_object_or_404(Athlete, pk=athlete_id, organization=self.organization)

        # Role gate: athletes may only access their own PMC
        if self.membership.role not in _WRITE_ROLES:
            if athlete.user_id != request.user.pk:
                raise NotFound()

        # Validate days param
        try:
            days = int(request.query_params.get("days", 90))
        except (TypeError, ValueError):
            raise DRFValidationError({"days": "Must be a positive integer."})
        if days < 1 or days > 365:
            raise DRFValidationError({"days": "Must be between 1 and 365."})

        from core import services_analytics

        data = services_analytics.compute_athlete_pmc_real(
            organization=self.organization,
            athlete=athlete,
            days=days,
        )
        return Response(
            {
                "athlete_id": athlete.pk,
                "organization_id": self.organization.pk,
                "days": days,
                "data": data,
            }
        )


# ==============================================================================
# PR-129: Strava Historical Backfill — coach-triggered async import
# URL: POST /api/p1/orgs/<org_id>/athletes/<athlete_id>/backfill/strava/
# ==============================================================================


class StravaBackfillView(OrgTenantMixin, views.APIView):
    """
    Enqueue a historical Strava backfill for a single athlete.

    Returns 202 Accepted immediately; backfill runs in a Celery worker.

    Role gate: owner/coach only — athletes may not trigger backfill.
    Tenancy: athlete is validated to belong to self.organization (fail-closed 404).

    Validations (400 Bad Request):
    - Athlete has no linked legacy Alumno profile (ingest pipeline requires it).
    - Athlete has no Strava credential (SocialToken or OAuthCredential).
    """

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def post(self, request, org_id: int, athlete_id: int):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can trigger backfill.")

        # Fail-closed: 404 if athlete not in this org
        athlete = get_object_or_404(Athlete, pk=athlete_id, organization=self.organization)

        # Bridge Athlete → legacy Alumno (required by ingest_strava_activity)
        alumno = getattr(athlete.user, "perfil_alumno", None)
        if alumno is None:
            return Response(
                {"detail": "no_legacy_profile"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check Strava connected — SocialToken (allauth primary) or OAuthCredential
        from allauth.socialaccount.models import SocialToken  # noqa: PLC0415

        has_strava = SocialToken.objects.filter(
            account__user=athlete.user, account__provider="strava"
        ).exists()
        if not has_strava:
            has_strava = OAuthCredential.objects.filter(
                alumno=alumno, provider="strava"
            ).exists()

        if not has_strava:
            return Response(
                {"detail": "strava_not_connected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lazy import: Law 4 — integrations/ never imported at module level in core/
        from integrations.strava.tasks_backfill import backfill_strava_athlete  # noqa: PLC0415

        task = backfill_strava_athlete.delay(
            organization_id=self.organization.pk,
            athlete_id=athlete.pk,
            alumno_id=alumno.pk,
        )

        return Response(
            {"status": "queued", "athlete_id": athlete.pk, "task_id": task.id},
            status=status.HTTP_202_ACCEPTED,
        )


# ==============================================================================
# PR-X4: ExternalIdentity ViewSet
# ==============================================================================


class ExternalIdentityViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD for ExternalIdentity records scoped to the authenticated coach's alumnos.

    Tenancy (dual-layer, fail-closed):
    - OrgTenantMixin.resolve_membership(org_id) validates active org membership.
    - get_queryset() filters by alumno__entrenador=request.user (legacy coach-scope).
      A coach only sees/modifies identities whose alumno belongs to them.

    Write: owner/coach only. Athletes cannot write.

    status and linked_at are auto-computed on create/update:
    - alumno provided → status=LINKED, linked_at=now()
    - alumno absent/null → status=UNLINKED, linked_at=None

    URL: /api/p1/orgs/<org_id>/external-identities/
    """

    serializer_class = ExternalIdentitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "swagger_fake_view", False):
            return
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        if not getattr(self, "organization", None):
            return ExternalIdentity.objects.none()
        return ExternalIdentity.objects.filter(
            alumno__entrenador=self.request.user
        ).order_by("-created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _require_write_role(self):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can manage external identities.")

    def perform_create(self, serializer):
        self._require_write_role()
        alumno = serializer.validated_data.get("alumno")
        link_status = ExternalIdentity.Status.LINKED if alumno else ExternalIdentity.Status.UNLINKED
        linked_at = timezone.now() if alumno else None
        serializer.save(status=link_status, linked_at=linked_at)

    def perform_update(self, serializer):
        self._require_write_role()
        # Determine new alumno value (may be absent on PATCH → keep existing).
        alumno = serializer.validated_data.get("alumno", serializer.instance.alumno)
        alumno_explicitly_cleared = (
            "alumno" in serializer.validated_data
            and serializer.validated_data["alumno"] is None
        )
        if alumno and serializer.instance.status != ExternalIdentity.Status.LINKED:
            serializer.save(
                status=ExternalIdentity.Status.LINKED,
                linked_at=timezone.now(),
            )
        elif alumno_explicitly_cleared:
            serializer.save(
                status=ExternalIdentity.Status.UNLINKED,
                linked_at=None,
            )
        else:
            serializer.save()

    def perform_destroy(self, instance):
        self._require_write_role()
        instance.delete()
