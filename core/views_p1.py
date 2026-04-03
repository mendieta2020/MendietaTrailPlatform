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
from django.db import models
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
    AthleteInjury,
    CompletedActivity,
    ExternalIdentity,
    OAuthCredential,
    PlannedWorkout,
    RaceEvent,
    Team,
    TrainingWeek,
    WellnessCheckIn,
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
    MacroRowSerializer,
    PlannedWorkoutReadSerializer,
    PlannedWorkoutWriteSerializer,
    RaceEventSerializer,
    TrainingWeekSerializer,
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


def _notify_coach_of_athlete_note(assignment, athlete_user, organization):
    """
    Send an InternalMessage to the athlete's coach when the athlete saves a
    non-empty note on a workout assignment.

    Recipient resolution (in order):
      1. assignment.athlete.coach.user  — directly assigned coach
      2. First active coach/owner Membership in the org  — fallback

    No notification is sent if no coach user can be resolved.
    """
    from core.models import InternalMessage, Membership  # noqa: PLC0415

    coach_user = None

    # 1. Primary: athlete's assigned coach
    if assignment.athlete and assignment.athlete.coach_id:
        try:
            coach_user = assignment.athlete.coach.user
        except Exception:  # noqa: BLE001
            pass

    # 2. Fallback: first active coach/owner in the org
    if coach_user is None:
        m = (
            Membership.objects.filter(
                organization=organization,
                role__in=_WRITE_ROLES,
                is_active=True,
            )
            .select_related("user")
            .first()
        )
        if m:
            coach_user = m.user

    if not coach_user or coach_user == athlete_user:
        return  # nothing to do

    workout_name = (
        assignment.planned_workout.name
        if assignment.planned_workout
        else "tu sesión"
    )
    InternalMessage.objects.create(
        organization=organization,
        sender=athlete_user,
        recipient=coach_user,
        content=f"💬 Nota en '{workout_name}': {assignment.athlete_notes}",
        alert_type="athlete_session_note",
        reference_id=assignment.pk,
        reference_date=assignment.scheduled_date,
    )


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
    Athletes can read and write their own goals only.
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
        else:
            athlete_id = self.request.query_params.get("athlete_id")
            if athlete_id:
                qs = qs.filter(athlete_id=athlete_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "organization", None):
            ctx["organization"] = self.organization
        return ctx

    def _get_athlete_for_self(self):
        """Return the Athlete record for the authenticated athlete user, or raise."""
        athlete = Athlete.objects.filter(
            organization=self.organization, user=self.request.user
        ).first()
        if not athlete:
            raise PermissionDenied("No athlete profile found.")
        return athlete

    def perform_create(self, serializer):
        if self.membership.role == "athlete":
            athlete = self._get_athlete_for_self()
            serializer.save(
                organization=self.organization,
                created_by=self.request.user,
                athlete=athlete,
            )
        else:
            if self.membership.role not in _WRITE_ROLES:
                raise PermissionDenied("Only coaches and owners can modify athlete goals.")
            serializer.save(
                organization=self.organization,
                created_by=self.request.user,
            )

    def perform_update(self, serializer):
        if self.membership.role == "athlete":
            # Athletes can only update their own goals (queryset already filters to theirs)
            serializer.save()
        else:
            if self.membership.role not in _WRITE_ROLES:
                raise PermissionDenied("Only coaches and owners can modify athlete goals.")
            serializer.save()

    def perform_destroy(self, instance):
        if self.membership.role == "athlete":
            # Athletes can only delete their own goals (queryset already filters to theirs)
            instance.delete()
        else:
            if self.membership.role not in _WRITE_ROLES:
                raise PermissionDenied("Only coaches and owners can modify athlete goals.")
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
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    List, retrieve, create, update, and delete WorkoutAssignment within an organization.

    PR-145f: destroy added. Completed assignments cannot be deleted (preserved as history).
    Use status="canceled" to retire an assignment without removing it.

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
        ).select_related("planned_workout", "athlete__user").prefetch_related(
            "planned_workout__blocks__intervals"
        )
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

    def list(self, request, *args, **kwargs):
        """
        PR-145d: Enrich upcoming assignments (today → +4 days) with OWM weather
        before serializing. Only assignments without a snapshot are enriched.
        Weather enrichment is best-effort and never blocks the response.
        """
        from core.services_weather import enrich_assignment_weather

        qs = self.filter_queryset(self.get_queryset())

        # Enrich upcoming assignments that have no weather snapshot yet
        today = datetime.date.today()
        upcoming_window = today + datetime.timedelta(days=4)
        to_enrich = (
            qs.filter(
                scheduled_date__gte=today,
                scheduled_date__lte=upcoming_window,
                weather_snapshot__isnull=True,
            )
            .select_related("athlete")
        )
        for assignment in to_enrich:
            try:
                enrich_assignment_weather(assignment)
            except Exception:
                pass  # graceful degradation — never break the list response

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can create workout assignments.")
        planned_workout = serializer.validated_data["planned_workout"]
        athlete = serializer.validated_data.get("athlete")
        scheduled_date = serializer.validated_data.get("scheduled_date")

        # Auto-calculate day_order to support double/triple sessions on the same day.
        # Count existing assignments for this athlete+date to determine next order slot.
        existing_count = WorkoutAssignment.objects.filter(
            organization=self.organization,
            athlete=athlete,
            scheduled_date=scheduled_date,
        ).count()

        try:
            serializer.save(
                organization=self.organization,
                assigned_by=self.request.user,
                snapshot_version=planned_workout.structure_version,
                day_order=existing_count + 1,
            )
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

    def perform_update(self, serializer):
        # Athletes can update their own (queryset already restricts to own).
        # The athlete serializer enforces write-only on athlete_notes + athlete_moved_date.
        # Coaches can update any assignment in the org.

        # Capture current athlete_notes before save (for change detection)
        old_athlete_notes = serializer.instance.athlete_notes or ""

        try:
            serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)}
            raise DRFValidationError(detail=detail)

        # Notify coach when athlete saves a non-empty note that has changed
        instance = serializer.instance
        new_notes = instance.athlete_notes or ""
        if (
            self.membership.role == "athlete"
            and new_notes
            and new_notes != old_athlete_notes
        ):
            _notify_coach_of_athlete_note(instance, self.request.user, self.organization)

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

    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/bulk-create/

        PR-145h: Assigns a PlannedWorkout to a list of specific athletes on a given date.
        Idempotent: if athlete already has an assignment for that workout+date, skip.

        Request body:
          {
            "athlete_ids": [1, 2, 3],
            "planned_workout_id": <int>,
            "scheduled_date": "YYYY-MM-DD"
          }

        Returns:
          { "created": <int>, "skipped": <int>, "assignments": [...] }
        """
        from django.db import transaction  # noqa: PLC0415

        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can bulk-create assignments.")

        athlete_ids = request.data.get("athlete_ids")
        planned_workout_id = request.data.get("planned_workout_id")
        # Accept "dates" (list) or legacy "scheduled_date" (single string).
        dates_raw = request.data.get("dates")
        scheduled_date_raw = request.data.get("scheduled_date")

        errors = {}
        if not athlete_ids or not isinstance(athlete_ids, list):
            errors["athlete_ids"] = "Must be a non-empty list."
        if not planned_workout_id:
            errors["planned_workout_id"] = "This field is required."
        if not dates_raw and not scheduled_date_raw:
            errors["dates"] = "Provide 'dates' (list) or 'scheduled_date' (string)."
        if errors:
            raise DRFValidationError(errors)

        # Normalize to a list of date objects.
        raw_list = dates_raw if dates_raw else [scheduled_date_raw]
        if not isinstance(raw_list, list) or not raw_list:
            raise DRFValidationError({"dates": "Must be a non-empty list of YYYY-MM-DD strings."})
        try:
            scheduled_dates = [datetime.date.fromisoformat(str(d)) for d in raw_list]
        except ValueError:
            raise DRFValidationError({"dates": "Invalid date format. Use YYYY-MM-DD."})

        planned_workout = get_object_or_404(
            PlannedWorkout,
            pk=planned_workout_id,
            organization=self.organization,
        )

        # Validate all athlete_ids belong to this org — fail-closed (Law 1).
        from core.models import Athlete  # noqa: PLC0415
        athletes = list(
            Athlete.objects.filter(
                pk__in=athlete_ids,
                organization=self.organization,
                is_active=True,
            ).select_related("user")
        )
        if len(athletes) != len(set(athlete_ids)):
            raise DRFValidationError(
                {"athlete_ids": "One or more athletes not found in this organization."}
            )

        created_assignments = []
        skipped = 0

        with transaction.atomic():
            for scheduled_date in scheduled_dates:
                for athlete in athletes:
                    # Idempotency: skip if same athlete+workout+date already exists.
                    if WorkoutAssignment.objects.filter(
                        organization=self.organization,
                        athlete=athlete,
                        planned_workout=planned_workout,
                        scheduled_date=scheduled_date,
                    ).exists():
                        skipped += 1
                        continue

                    existing_count = WorkoutAssignment.objects.filter(
                        organization=self.organization,
                        athlete=athlete,
                        scheduled_date=scheduled_date,
                    ).count()

                    assignment = WorkoutAssignment.objects.create(
                        organization=self.organization,
                        athlete=athlete,
                        planned_workout=planned_workout,
                        scheduled_date=scheduled_date,
                        assigned_by=request.user,
                        snapshot_version=planned_workout.structure_version,
                        day_order=existing_count + 1,
                    )
                    created_assignments.append(assignment)

        # Re-fetch with select_related for serialization.
        created_ids = [a.pk for a in created_assignments]
        assignments_qs = WorkoutAssignment.objects.filter(
            pk__in=created_ids
        ).select_related("planned_workout", "athlete__user").prefetch_related(
            "planned_workout__blocks__intervals"
        )
        serializer = WorkoutAssignmentSerializer(
            assignments_qs, many=True, context=self.get_serializer_context()
        )
        return Response(
            {
                "created": len(created_assignments),
                "skipped": skipped,
                "assignments": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/p1/orgs/<org_id>/assignments/<pk>/

        PR-145f: Coaches and owners can delete planned assignments.
        Completed assignments are protected — use status="canceled" instead.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can delete assignments.")
        instance = self.get_object()
        if instance.status == WorkoutAssignment.Status.COMPLETED:
            return Response(
                {"detail": "No se puede eliminar una sesión completada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="clone-workout")
    def clone_workout(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/<pk>/clone-workout/

        PR-145f: Clones the PlannedWorkout of this assignment and points the
        assignment at the clone. The original library workout remains untouched.
        The coach can then edit the clone without affecting other athletes.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can clone workouts.")

        assignment = self.get_object()
        original = assignment.planned_workout

        if original is None:
            return Response(
                {"detail": "Sin workout planificado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Skip clone if already a snapshot
        if original.is_assignment_snapshot:
            serializer = WorkoutAssignmentSerializer(
                assignment, context=self.get_serializer_context()
            )
            return Response(serializer.data)

        # Clone the PlannedWorkout (detached from library)
        clone = PlannedWorkout.objects.get(pk=original.pk)
        clone.pk = None
        clone.name = f"{original.name} (personalizado)"
        clone.is_assignment_snapshot = True
        clone.library = None
        clone.save()

        # Clone blocks and intervals
        for block in original.blocks.prefetch_related("intervals").all():
            original_block_pk = block.pk
            block.pk = None
            block.planned_workout = clone
            block.save()
            for interval in WorkoutBlock.objects.get(pk=original_block_pk).intervals.all():
                interval.pk = None
                interval.block = block
                interval.save()

        # Point assignment at the clone
        assignment.planned_workout = clone
        assignment.save(update_fields=["planned_workout"])

        serializer = WorkoutAssignmentSerializer(
            assignment, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="copy-week")
    def copy_week(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/copy-week/

        PR-145f: Copies all planned assignments for a source athlete in a date
        range to a target athlete starting at target_week_start.
        Completed assignments are never copied.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can copy weeks.")

        source_athlete_id = request.data.get("source_athlete_id")
        source_date_from = request.data.get("source_date_from")
        source_date_to = request.data.get("source_date_to")
        target_athlete_id = request.data.get("target_athlete_id")
        target_week_start = request.data.get("target_week_start")

        errors = {}
        if not source_athlete_id:
            errors["source_athlete_id"] = "This field is required."
        if not source_date_from:
            errors["source_date_from"] = "This field is required."
        if not source_date_to:
            errors["source_date_to"] = "This field is required."
        if not target_athlete_id:
            errors["target_athlete_id"] = "This field is required."
        if not target_week_start:
            errors["target_week_start"] = "This field is required."
        if errors:
            raise DRFValidationError(errors)

        try:
            source_from = datetime.date.fromisoformat(str(source_date_from))
            source_to = datetime.date.fromisoformat(str(source_date_to))
            target_start = datetime.date.fromisoformat(str(target_week_start))
        except ValueError as exc:
            raise DRFValidationError({"detail": f"Invalid date format: {exc}"})

        source_athlete = get_object_or_404(
            Athlete, pk=source_athlete_id, organization=self.organization
        )
        target_athlete = get_object_or_404(
            Athlete, pk=target_athlete_id, organization=self.organization
        )

        delta = target_start - source_from

        # All assignments are copied regardless of status (planned or completed).
        # New assignments are always created as PLANNED with no actual_* data.
        source_assignments = (
            WorkoutAssignment.objects.filter(
                organization=self.organization,
                athlete=source_athlete,
                scheduled_date__gte=source_from,
                scheduled_date__lte=source_to,
            )
            .select_related("planned_workout")
        )

        created = []
        for src in source_assignments:
            new_date = src.scheduled_date + delta
            existing_count = WorkoutAssignment.objects.filter(
                organization=self.organization,
                athlete=target_athlete,
                scheduled_date=new_date,
            ).count()
            new_assignment = WorkoutAssignment(
                organization=self.organization,
                athlete=target_athlete,
                planned_workout=src.planned_workout,
                scheduled_date=new_date,
                day_order=existing_count + 1,
                assigned_by=request.user,
                status=WorkoutAssignment.Status.PLANNED,
            )
            new_assignment.save()
            created.append(new_assignment)

        serializer = WorkoutAssignmentSerializer(
            created, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="delete-week")
    def delete_week(self, request, *args, **kwargs):
        """
        POST /api/p1/orgs/<org_id>/assignments/delete-week/

        PR-145f: Deletes planned assignments for an athlete in a date range.
        Completed assignments are never deleted.
        Returns counts of deleted and protected (completed) assignments.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can delete weeks.")

        athlete_id = request.data.get("athlete_id")
        date_from = request.data.get("date_from")
        date_to = request.data.get("date_to")

        errors = {}
        if not athlete_id:
            errors["athlete_id"] = "This field is required."
        if not date_from:
            errors["date_from"] = "This field is required."
        if not date_to:
            errors["date_to"] = "This field is required."
        if errors:
            raise DRFValidationError(errors)

        try:
            d_from = datetime.date.fromisoformat(str(date_from))
            d_to = datetime.date.fromisoformat(str(date_to))
        except ValueError as exc:
            raise DRFValidationError({"detail": f"Invalid date format: {exc}"})

        athlete = get_object_or_404(
            Athlete, pk=athlete_id, organization=self.organization
        )

        to_delete = WorkoutAssignment.objects.filter(
            organization=self.organization,
            athlete=athlete,
            scheduled_date__gte=d_from,
            scheduled_date__lte=d_to,
        ).exclude(status=WorkoutAssignment.Status.COMPLETED)

        protected = WorkoutAssignment.objects.filter(
            organization=self.organization,
            athlete=athlete,
            scheduled_date__gte=d_from,
            scheduled_date__lte=d_to,
            status=WorkoutAssignment.Status.COMPLETED,
        ).count()

        deleted_count = to_delete.count()
        to_delete.delete()

        return Response({"deleted": deleted_count, "protected_completed": protected})

    @action(detail=True, methods=["patch"], url_path="update-snapshot")
    def update_snapshot(self, request, *args, **kwargs):
        """
        PATCH /api/p1/orgs/<org_id>/assignments/<pk>/update-snapshot/

        Update the PlannedWorkout snapshot linked to this assignment.
        Accepts workout metadata + optional `blocks` array with nested intervals.
        Handles the full replace atomically (delete old blocks, create new ones).

        Guards:
        - write role required (coach / owner)
        - workout must be is_assignment_snapshot=True
        - Plan ≠ Real: never touches CompletedActivity
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can edit assignment snapshots.")

        assignment = self.get_object()
        pw = assignment.planned_workout

        if not pw:
            return Response({"detail": "Esta sesión no tiene workout asociado."}, status=400)
        if not pw.is_assignment_snapshot:
            return Response(
                {"detail": "Solo se pueden editar sesiones personalizadas (snapshot)."},
                status=400,
            )

        # Update workout metadata (partial — only provided fields are written).
        blocks_data = request.data.pop("blocks", None) if isinstance(request.data, dict) else None
        serializer = PlannedWorkoutWriteSerializer(
            pw, data=request.data, partial=True,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        pw = serializer.save()

        # Replace blocks + intervals atomically if blocks payload is provided.
        if blocks_data is not None:
            pw.blocks.all().delete()
            for block_dict in blocks_data:
                intervals_data = block_dict.pop("intervals", [])
                block = WorkoutBlock.objects.create(
                    organization=self.organization,
                    planned_workout=pw,
                    name=block_dict.get("name", ""),
                    block_type=block_dict.get("block_type", "custom"),
                    order_index=block_dict.get("order_index", 1),
                    repetitions=block_dict.get("repetitions", 1),
                )
                for iv_dict in intervals_data:
                    WorkoutInterval.objects.create(
                        organization=self.organization,
                        block=block,
                        **{k: v for k, v in iv_dict.items() if k not in ("id",)},
                    )

        pw.refresh_from_db()
        return Response(PlannedWorkoutReadSerializer(pw, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["patch"], url_path="coach-comment")
    def add_coach_comment(self, request, *args, **kwargs):
        """
        PATCH /api/p1/orgs/<org_id>/assignments/<pk>/coach-comment/

        El coach deja o actualiza su comentario en una sesión.
        Cualquier sesión (planned o completed) puede tener comentario.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Solo coaches y owners pueden comentar.")

        comment = request.data.get("coach_comment", "")
        assignment = self.get_object()
        assignment.coach_comment = comment
        assignment.coach_commented_at = timezone.now() if comment else None
        assignment.save(update_fields=["coach_comment", "coach_commented_at"])

        # Notify the athlete via InternalMessage when coach leaves a non-empty comment
        if comment and assignment.athlete and assignment.athlete.user_id:
            from core.models import InternalMessage  # noqa: PLC0415
            workout_name = (
                assignment.planned_workout.name
                if assignment.planned_workout
                else "tu sesión"
            )
            InternalMessage.objects.create(
                organization=self.organization,
                sender=request.user,
                recipient_id=assignment.athlete.user_id,
                content=f"📋 Comentario en '{workout_name}': {comment}",
                alert_type="session_comment",
                reference_id=assignment.pk,
                reference_date=assignment.scheduled_date,
            )

        return Response({
            "coach_comment": assignment.coach_comment,
            "coach_commented_at": assignment.coach_commented_at,
        })


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


# ==============================================================================
# PR-153: AthleteInjury + Availability ViewSets
# ==============================================================================


class AthleteInjuryViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    CRUD /api/p1/orgs/<org_id>/athletes/<athlete_id>/injuries/
    Athletes can manage their own injuries. Coaches can view all.
    Membership is resolved once in initial() and cached on self.organization.
    """
    serializer_class = None

    def get_serializer_class(self):
        from core.serializers_p1 import AthleteInjurySerializer
        return AthleteInjurySerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])  # caches self.organization

    def get_queryset(self):
        from core.models import AthleteInjury
        return AthleteInjury.objects.filter(
            organization=self.organization, athlete_id=self.kwargs["athlete_id"],
        )

    def perform_create(self, serializer):
        from core.models import Athlete
        athlete = Athlete.objects.get(
            pk=self.kwargs["athlete_id"], organization=self.organization,
        )
        serializer.save(athlete=athlete, organization=self.organization)


import logging as _logging
_avail_logger = _logging.getLogger(__name__)


class AthleteAvailabilityListView(OrgTenantMixin, viewsets.ModelViewSet):
    """
    GET /api/p1/orgs/<org_id>/athletes/<athlete_id>/availability/
        Returns 7-day availability for the athlete.
    PUT /api/p1/orgs/<org_id>/athletes/<athlete_id>/availability/
        Replaces all availability records atomically (delete-all + create).
        Accepts list of {day_of_week, is_available, reason, preferred_time}.
    """
    serializer_class = None

    def get_serializer_class(self):
        from core.serializers_p1 import AthleteAvailabilitySerializer
        return AthleteAvailabilitySerializer

    def get_queryset(self):
        from core.models import AthleteAvailability
        org = self.resolve_membership(self.kwargs["org_id"]).organization
        athlete_id = self.kwargs["athlete_id"]
        return AthleteAvailability.objects.filter(
            organization=org, athlete_id=athlete_id,
        ).order_by("day_of_week")

    def bulk_update(self, request, *args, **kwargs):
        """
        PUT: replace all 7-day availability records for this athlete.
        Runs inside a single transaction: delete existing → create new.
        Tenancy: org derived from authenticated membership, never from body.
        """
        from django.db import transaction
        from core.models import AthleteAvailability, Athlete

        membership = self.resolve_membership(self.kwargs["org_id"])
        org = membership.organization
        athlete = get_object_or_404(
            Athlete, pk=self.kwargs["athlete_id"], organization=org
        )

        serializer_cls = self.get_serializer_class()
        serializer = serializer_cls(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            AthleteAvailability.objects.filter(
                athlete=athlete, organization=org
            ).delete()
            for item in serializer.validated_data:
                AthleteAvailability.objects.create(
                    athlete=athlete,
                    organization=org,
                    **item,
                )

        _avail_logger.info(
            "athlete_availability.bulk_updated",
            extra={
                "event_name": "athlete_availability.bulk_updated",
                "organization_id": org.id,
                "actor_id": request.user.id,
                "athlete_id": athlete.id,
                "outcome": "success",
            },
        )

        result_qs = AthleteAvailability.objects.filter(
            athlete=athlete, organization=org
        ).order_by("day_of_week")
        out = serializer_cls(result_qs, many=True)
        return Response(out.data)


# ==============================================================================
# PR-154: WellnessCheckIn ViewSets
# ==============================================================================

import logging as _wellness_logging
_wellness_logger = _wellness_logging.getLogger(__name__)


class WellnessCheckInViewSet(OrgTenantMixin, viewsets.ModelViewSet):
    """
    POST   /api/p1/orgs/<org_id>/athletes/<athlete_id>/wellness/
        Create today's check-in for the athlete. Idempotent: returns 200 if
        a check-in for today already exists.
    GET    /api/p1/orgs/<org_id>/athletes/<athlete_id>/wellness/?days=7
        Return last N days of check-ins (default 7, max 90).

    Athlete: may only manage their own check-in.
    Coach/owner: read-only access to any athlete's check-ins.
    """
    serializer_class = None
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        from core.serializers_p1 import WellnessCheckInSerializer
        return WellnessCheckInSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def get_queryset(self):
        from core.models import WellnessCheckIn
        import datetime
        qs = WellnessCheckIn.objects.filter(
            organization=self.organization,
            athlete_id=self.kwargs["athlete_id"],
        )
        try:
            days = min(int(self.request.query_params.get("days", 7)), 90)
        except (TypeError, ValueError):
            days = 7
        cutoff = datetime.date.today() - datetime.timedelta(days=days - 1)
        return qs.filter(date__gte=cutoff).order_by("-date")

    def create(self, request, *args, **kwargs):
        import datetime
        from core.models import Athlete, WellnessCheckIn
        from core.serializers_p1 import WellnessCheckInSerializer

        athlete = get_object_or_404(
            Athlete,
            pk=self.kwargs["athlete_id"],
            organization=self.organization,
        )
        # Enforce: athletes can only submit their own check-in
        if self.membership.role == "athlete" and athlete.user != request.user:
            raise PermissionDenied("Athletes can only submit their own wellness check-in.")

        today = datetime.date.today()
        # Merge today's date into the payload if not provided by the client
        data = {**request.data, "date": request.data.get("date", str(today))}
        try:
            parsed_date = datetime.date.fromisoformat(str(data["date"]))
        except (ValueError, TypeError):
            parsed_date = today
            data["date"] = str(today)

        existing = WellnessCheckIn.objects.filter(
            athlete=athlete, organization=self.organization, date=parsed_date
        ).first()
        if existing:
            # Upsert: update and return 200
            serializer = WellnessCheckInSerializer(existing, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = WellnessCheckInSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(athlete=athlete, organization=self.organization)
        _wellness_logger.info(
            "wellness.created",
            extra={
                "event_name": "wellness.created",
                "organization_id": self.organization.id,
                "actor_id": request.user.id,
                "athlete_id": athlete.id,
                "date": str(parsed_date),
                "outcome": "success",
            },
        )
        return Response(WellnessCheckInSerializer(obj).data, status=status.HTTP_201_CREATED)


class WellnessDismissView(OrgTenantMixin, views.APIView):
    """
    POST /api/p1/orgs/<org_id>/athletes/<athlete_id>/wellness/dismiss/
    Permanently opt the athlete out of the daily wellness check-in prompt.
    Athletes can only dismiss their own. Coaches can dismiss on behalf of athlete.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, org_id, athlete_id):
        from core.models import Athlete, AthleteProfile

        self.resolve_membership(org_id)
        athlete = get_object_or_404(
            Athlete, pk=athlete_id, organization=self.organization
        )

        if self.membership.role == "athlete" and athlete.user != request.user:
            raise PermissionDenied("Athletes can only dismiss their own wellness prompt.")

        profile, _ = AthleteProfile.objects.get_or_create(
            athlete=athlete,
            defaults={"organization": self.organization},
        )
        profile.wellness_checkin_dismissed = True
        profile.save(update_fields=["wellness_checkin_dismissed"])

        _wellness_logger.info(
            "wellness.dismissed",
            extra={
                "event_name": "wellness.dismissed",
                "organization_id": self.organization.id,
                "actor_id": request.user.id,
                "athlete_id": athlete.id,
                "outcome": "success",
            },
        )
        return Response({"dismissed": True})


# ==============================================================================
# PR-155: TrainingWeek — macro periodization phase per athlete per week
# ==============================================================================

import logging as _tw_logging
_tw_logger = _tw_logging.getLogger(__name__)


class TrainingWeekViewSet(OrgTenantMixin, viewsets.GenericViewSet):
    """
    GET  /api/p1/orgs/<org_id>/training-weeks/?week_start=2026-04-07
        Returns one aggregated MacroRow per athlete in the org (or filtered
        by team_id query param) for the requested week_start (Monday).
        Includes: phase, goal A, days until race, active injury flag,
        wellness 7-day average.

    POST /api/p1/orgs/<org_id>/training-weeks/
        Upsert a phase for one athlete for one week.
        Body: { athlete_id, week_start, phase, notes? }
        Idempotent: update_or_create on (athlete, week_start).

    Coach/owner only for writes. Coach/owner/athlete for reads (athletes
    see only their own row).
    """
    serializer_class = TrainingWeekSerializer
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.resolve_membership(self.kwargs["org_id"])

    def list(self, request, org_id):
        """
        GET /api/p1/orgs/<org_id>/training-weeks/?week_start=YYYY-MM-DD
        Returns aggregated MacroRow list.
        """
        # Parse week_start — default to current Monday
        today = datetime.date.today()
        default_monday = today - datetime.timedelta(days=today.weekday())
        week_start_str = request.query_params.get("week_start", str(default_monday))
        try:
            week_start = datetime.date.fromisoformat(week_start_str)
        except ValueError:
            raise DRFValidationError({"week_start": "Must be YYYY-MM-DD."})
        # Snap to Monday if not already
        if week_start.weekday() != 0:
            week_start = week_start - datetime.timedelta(days=week_start.weekday())

        week_end = week_start + datetime.timedelta(days=6)

        # Optional team filter
        team_id = request.query_params.get("team_id")

        # Fetch all active athletes in the org (role-gated: athletes see only self)
        athletes_qs = Athlete.objects.filter(
            organization=self.organization,
            is_active=True,
        ).select_related("user", "profile")
        if team_id:
            athletes_qs = athletes_qs.filter(team_id=team_id)
        if self.membership.role == "athlete":
            athletes_qs = athletes_qs.filter(user=request.user)

        athlete_ids = list(athletes_qs.values_list("id", flat=True))

        # PR-157 hotfix: batch fetch membership_id for each athlete (for recent-workouts endpoint)
        from core.models import Membership as _Membership
        membership_map = {
            m["user_id"]: m["id"]
            for m in _Membership.objects.filter(
                organization=self.organization,
                user_id__in=athletes_qs.values_list("user_id", flat=True),
                role=_Membership.Role.ATHLETE,
                is_active=True,
            ).values("user_id", "id")
        }

        # Batch fetch training weeks for this week_start
        tw_map = {
            tw.athlete_id: tw
            for tw in TrainingWeek.objects.filter(
                organization=self.organization,
                athlete_id__in=athlete_ids,
                week_start=week_start,
            )
        }

        # Batch fetch next goal (nearest date, any priority, active/planned)
        all_goals_qs = list(
            AthleteGoal.objects.filter(
                organization=self.organization,
                athlete_id__in=athlete_ids,
                status__in=[AthleteGoal.Status.ACTIVE, AthleteGoal.Status.PLANNED],
            ).select_related("target_event")
        )

        def _effective_date(g):
            d = g.target_date or (g.target_event.event_date if g.target_event_id else None)
            return d or datetime.date.max

        all_goals_qs.sort(key=lambda g: (g.athlete_id, _effective_date(g)))
        goal_map = {}
        all_goals_map = {}
        for g in all_goals_qs:
            if g.athlete_id not in goal_map:
                goal_map[g.athlete_id] = g
            all_goals_map.setdefault(g.athlete_id, []).append(g)

        # Batch fetch active injuries
        injury_athlete_ids = set(
            AthleteInjury.objects.filter(
                organization=self.organization,
                athlete_id__in=athlete_ids,
                status=AthleteInjury.Status.ACTIVA,
            ).values_list("athlete_id", flat=True)
        )

        # Batch fetch wellness 7-day average per athlete
        cutoff = today - datetime.timedelta(days=6)
        from django.db.models import Avg
        wellness_avgs = dict(
            WellnessCheckIn.objects.filter(
                organization=self.organization,
                athlete_id__in=athlete_ids,
                date__gte=cutoff,
            )
            .values("athlete_id")
            .annotate(
                avg=Avg(
                    (
                        models.F("sleep_quality")
                        + models.F("mood")
                        + models.F("energy")
                        + models.F("muscle_soreness")
                        + models.F("stress")
                    ) / 5.0
                )
            )
            .values_list("athlete_id", "avg")
        )

        rows = []
        for athlete in athletes_qs:
            tw = tw_map.get(athlete.id)
            goal = goal_map.get(athlete.id)
            goal_date = None
            if goal:
                goal_date = goal.target_date or (
                    goal.target_event.event_date if goal.target_event_id else None
                )
            days_until = None
            if goal_date:
                days_until = (goal_date - today).days

            full_name = athlete.user.get_full_name() or athlete.user.username
            all_goals_brief = [
                {
                    "title": g.title,
                    "priority": g.priority,
                    "days": (_effective_date(g) - today).days if _effective_date(g) != datetime.date.max else None,
                }
                for g in all_goals_map.get(athlete.id, [])
            ]
            rows.append({
                "athlete_id": athlete.id,
                "membership_id": membership_map.get(athlete.user_id),
                "athlete_name": full_name,
                "phase": tw.phase if tw else None,
                "notes": tw.notes if tw else None,
                "training_week_id": tw.id if tw else None,
                "goal_a_title": goal.title if goal else None,
                "goal_a_priority": goal.priority if goal else None,
                "goal_a_date": goal_date,
                "goal_a_distance_km": goal.target_distance_km if goal else None,
                "goal_a_elevation_m": goal.target_elevation_gain_m if goal else None,
                "days_until_race": days_until,
                "has_active_injury": athlete.id in injury_athlete_ids,
                "wellness_avg": round(wellness_avgs.get(athlete.id, None) or 0, 2) if athlete.id in wellness_avgs else None,
                "all_goals_brief": all_goals_brief,
            })

        serializer = MacroRowSerializer(rows, many=True)
        return Response(serializer.data)

    def create(self, request, org_id):
        """
        POST /api/p1/orgs/<org_id>/training-weeks/
        Upsert training week phase for one athlete. Coach/owner only.
        """
        if self.membership.role not in _WRITE_ROLES:
            raise PermissionDenied("Only coaches and owners can assign training phases.")

        athlete_id = request.data.get("athlete_id")
        week_start_str = request.data.get("week_start")
        phase = request.data.get("phase")
        notes = request.data.get("notes", "")

        if not athlete_id or not week_start_str or not phase:
            raise DRFValidationError({"detail": "athlete_id, week_start, and phase are required."})

        try:
            week_start = datetime.date.fromisoformat(str(week_start_str))
        except ValueError:
            raise DRFValidationError({"week_start": "Must be YYYY-MM-DD."})

        athlete = get_object_or_404(
            Athlete, pk=athlete_id, organization=self.organization
        )

        if phase not in TrainingWeek.Phase.values:
            raise DRFValidationError({"phase": f"Must be one of: {TrainingWeek.Phase.values}"})

        # Snap to Monday
        if week_start.weekday() != 0:
            week_start = week_start - datetime.timedelta(days=week_start.weekday())

        tw, created = TrainingWeek.objects.update_or_create(
            athlete=athlete,
            week_start=week_start,
            defaults={
                "organization": self.organization,
                "phase": phase,
                "notes": notes,
            },
        )

        _tw_logger.info(
            "training_week.upserted",
            extra={
                "event_name": "training_week.upserted",
                "organization_id": self.organization.id,
                "actor_id": request.user.id,
                "athlete_id": athlete.id,
                "week_start": str(week_start),
                "phase": phase,
                "created": created,
                "outcome": "success",
            },
        )

        serializer = TrainingWeekSerializer(tw)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
