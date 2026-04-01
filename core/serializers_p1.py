"""
core/serializers_p1.py

Serializers for the P1 organization-first domain: RaceEvent, AthleteGoal,
AthleteProfile, and WorkoutAssignment.

Design rules enforced here:
- organization is NEVER a client-controlled field; it is injected by the ViewSet.
- FK querysets are scoped to the request organization via serializer
  context["organization"]. The model's clean() provides a second enforcement layer.
- No depth > 0: related objects are exposed as PKs only.
- created_by / updated_by / assigned_by are set by the ViewSet; not writable by the client.
"""

from rest_framework import serializers

from core.models import (
    Alumno,
    Athlete,
    AthleteGoal,
    AthleteProfile,
    ExternalIdentity,
    PlannedWorkout,
    RaceEvent,
    TrainingWeek,
    WellnessCheckIn,
    WorkoutAssignment,
    WorkoutBlock,
    WorkoutInterval,
    WorkoutLibrary,
    WorkoutReconciliation,
)


class RaceEventSerializer(serializers.ModelSerializer):
    """
    Serializer for RaceEvent.

    organization and created_by are injected by the ViewSet in perform_create.
    They are never accepted from the client.
    """

    class Meta:
        model = RaceEvent
        fields = [
            "id",
            "name",
            "discipline",
            "event_date",
            "location",
            "country",
            "distance_km",
            "elevation_gain_m",
            "event_url",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AthleteGoalSerializer(serializers.ModelSerializer):
    """
    Serializer for AthleteGoal.

    athlete_id and target_event_id are PrimaryKeyRelatedFields whose querysets
    are scoped to context["organization"] to prevent cross-org writes at the
    serializer layer. The model's clean() provides a second enforcement layer.

    organization and created_by are injected by the ViewSet; not client-writable.
    """

    athlete_id = serializers.PrimaryKeyRelatedField(
        source="athlete",
        queryset=Athlete.objects.none(),
    )
    target_event_id = serializers.PrimaryKeyRelatedField(
        source="target_event",
        queryset=RaceEvent.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = AthleteGoal
        fields = [
            "id",
            "title",
            "athlete_id",
            "priority",
            "goal_type",
            "status",
            "target_date",
            "target_event_id",
            "coach_notes",
            "target_distance_km",
            "target_elevation_gain_m",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # Suppress the auto-generated conditional UniqueConstraint validator for
        # ("athlete", "priority", status="active"). It raises KeyError on PATCH
        # because `status` is absent from partial data. The model's full_clean()
        # (called by save()) and the DB constraint are sufficient enforcement.
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["athlete_id"].queryset = Athlete.objects.filter(
                organization=organization
            )
            self.fields["target_event_id"].queryset = RaceEvent.objects.filter(
                organization=organization
            )


class AthleteProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for AthleteProfile.

    athlete_id is a PrimaryKeyRelatedField whose queryset is scoped to
    context["organization"]. On updates (instance is not None), athlete_id
    becomes read-only — profiles cannot be reassigned to a different athlete.

    organization and updated_by are injected by the ViewSet. They are never
    accepted from the client. updated_by_id is exposed as read-only for audit.

    JSON zone fields (hr_zones_json, pace_zones_json, power_zones_json) round-trip
    as raw JSON. No automatic recalculation is performed in this PR.
    """

    athlete_id = serializers.PrimaryKeyRelatedField(
        source="athlete",
        queryset=Athlete.objects.none(),  # overridden in __init__ from context
    )
    updated_by_id = serializers.PrimaryKeyRelatedField(
        source="updated_by",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AthleteProfile
        fields = [
            "id",
            "athlete_id",
            # Demographics
            "birth_date",
            "age",
            "height_cm",
            "weight_kg",
            "bmi",
            # Cardiovascular
            "resting_hr_bpm",
            "max_hr_bpm",
            # Performance
            "vo2max",
            "ftp_watts",
            "vam",
            "lactate_threshold_pace_s_per_km",
            "running_economy",
            "training_age_years",
            "dominant_discipline",
            # Injury state
            "is_injured",
            "injury_notes",
            # Training zones (raw JSON)
            "hr_zones_json",
            "pace_zones_json",
            "power_zones_json",
            # PR-149: Extended onboarding fields
            "blood_type",
            "clothing_size",
            "instagram_handle",
            "profession",
            "emergency_contact_name",
            "emergency_contact_phone",
            "pace_1000m_seconds",
            "weekly_available_hours",
            "preferred_training_time",
            "best_10k_minutes",
            "best_21k_minutes",
            "best_42k_minutes",
            "menstrual_tracking_enabled",
            "menstrual_cycle_days",
            "last_period_date",
            # Audit / notes
            "notes",
            "updated_by_id",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_by_id", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["athlete_id"].queryset = Athlete.objects.filter(
                organization=organization
            )
        # Athlete cannot be reassigned after profile creation.
        if self.instance is not None:
            self.fields["athlete_id"].read_only = True
            self.fields["athlete_id"].required = False


# ==============================================================================
# PR-153: AthleteInjury serializer
# ==============================================================================

from core.models import AthleteInjury, AthleteAvailability


class AthleteInjurySerializer(serializers.ModelSerializer):
    class Meta:
        model = AthleteInjury
        fields = [
            "id", "injury_type", "body_zone", "side", "severity",
            "description", "date_occurred", "status", "resolved_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AthleteAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AthleteAvailability
        fields = [
            "id", "day_of_week", "is_available", "reason", "preferred_time",
        ]
        read_only_fields = ["id"]


class WellnessCheckInSerializer(serializers.ModelSerializer):
    """
    Serializer for WellnessCheckIn.

    organization and athlete are injected by the ViewSet in perform_create.
    They are never accepted from the client.
    date defaults to today if not supplied; client may override for backfill.
    """

    class Meta:
        model = WellnessCheckIn
        fields = [
            "id",
            "date",
            "sleep_quality",
            "mood",
            "energy",
            "muscle_soreness",
            "stress",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


# ==============================================================================
# PR-117: WorkoutAssignment serializers
# ==============================================================================

_ASSIGNMENT_FIELDS = [
    "id",
    "athlete_id",
    "planned_workout_id",
    "planned_workout_title",
    "planned_workout",
    "assigned_by_id",
    "scheduled_date",
    "athlete_moved_date",
    "day_order",
    "status",
    "coach_notes",
    "athlete_notes",
    "target_zone_override",
    "target_pace_override",
    "target_rpe_override",
    "target_power_override",
    "snapshot_version",
    # PR-145d: actual execution data
    "actual_duration_seconds",
    "actual_distance_meters",
    "actual_elevation_gain",
    "rpe",
    "compliance_color",
    "weather_snapshot",
    # PR-145g: coach comment
    "coach_comment",
    "coach_commented_at",
    # PR-145g-fix: athlete display name (read-only, derived from athlete.user)
    "athlete_name",
    "assigned_at",
    "updated_at",
    "effective_date",
]


# ==============================================================================
# PR-128: WorkoutLibrary + PlannedWorkout CRUD serializers
# ==============================================================================


class WorkoutIntervalSerializer(serializers.ModelSerializer):
    """
    Read/write serializer for WorkoutInterval.

    block and organization are not exposed — injected by WorkoutIntervalViewSet.
    """

    class Meta:
        model = WorkoutInterval
        fields = [
            "id",
            "order_index",
            "repetitions",
            "metric_type",
            "description",
            "duration_seconds",
            "distance_meters",
            "target_value_low",
            "target_value_high",
            "target_label",
            "recovery_seconds",
            "recovery_distance_meters",
            "video_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkoutBlockSerializer(serializers.ModelSerializer):
    """
    Write serializer for WorkoutBlock.

    planned_workout and organization are not exposed — injected by WorkoutBlockViewSet.
    """

    class Meta:
        model = WorkoutBlock
        fields = [
            "id",
            "order_index",
            "block_type",
            "name",
            "repetitions",
            "description",
            "video_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkoutBlockReadSerializer(serializers.ModelSerializer):
    """
    Read serializer for WorkoutBlock with nested intervals.
    """

    intervals = WorkoutIntervalSerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutBlock
        fields = [
            "id",
            "order_index",
            "block_type",
            "name",
            "repetitions",
            "description",
            "video_url",
            "intervals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "intervals", "created_at", "updated_at"]


class WorkoutLibrarySerializer(serializers.ModelSerializer):
    """
    Serializer for WorkoutLibrary.

    organization is not exposed — injected by WorkoutLibraryViewSet.
    created_by_id is read-only — set by the ViewSet in perform_create.
    """

    created_by_id = serializers.PrimaryKeyRelatedField(
        source="created_by",
        read_only=True,
    )
    workout_count = serializers.SerializerMethodField()

    def get_workout_count(self, obj):
        return obj.planned_workouts.count()

    class Meta:
        model = WorkoutLibrary
        fields = [
            "id",
            "name",
            "description",
            "is_public",
            "created_by_id",
            "workout_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_id", "workout_count", "created_at", "updated_at"]


class PlannedWorkoutWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for PlannedWorkout.

    library and organization are URL-derived — injected by PlannedWorkoutViewSet
    in perform_create and never accepted from the client.
    created_by_id is read-only — set by the ViewSet in perform_create.
    """

    created_by_id = serializers.PrimaryKeyRelatedField(
        source="created_by",
        read_only=True,
    )

    class Meta:
        model = PlannedWorkout
        fields = [
            "id",
            "name",
            "description",
            "discipline",
            "session_type",
            "estimated_duration_seconds",
            "estimated_distance_meters",
            "difficulty",
            "elevation_gain_min_m",
            "elevation_gain_max_m",
            "primary_target_variable",
            "planned_tss",
            "planned_if",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_id", "created_at", "updated_at"]


class PlannedWorkoutReadSerializer(serializers.ModelSerializer):
    """
    Read serializer for PlannedWorkout with nested blocks.

    library_id is read-only. blocks uses WorkoutBlockReadSerializer for
    the full nested structure (blocks → intervals).
    """

    created_by_id = serializers.PrimaryKeyRelatedField(
        source="created_by",
        read_only=True,
    )
    library_id = serializers.PrimaryKeyRelatedField(
        source="library",
        read_only=True,
    )
    blocks = WorkoutBlockReadSerializer(many=True, read_only=True)

    class Meta:
        model = PlannedWorkout
        fields = [
            "id",
            "library_id",
            "name",
            "description",
            "discipline",
            "session_type",
            "estimated_duration_seconds",
            "estimated_distance_meters",
            "difficulty",
            "elevation_gain_min_m",
            "elevation_gain_max_m",
            "primary_target_variable",
            "planned_tss",
            "planned_if",
            "blocks",
            "is_assignment_snapshot",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "library_id",
            "blocks",
            "is_assignment_snapshot",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class WorkoutAssignmentSerializer(serializers.ModelSerializer):
    """
    Coach-write serializer for WorkoutAssignment.

    - athlete_id and planned_workout_id querysets are scoped to
      context["organization"] to prevent cross-org writes.
    - assigned_by_id, snapshot_version, assigned_at, updated_at: read-only
      (server-controlled; injected by the ViewSet).
    - scheduled_date: writable on create, read-only on update.
    - effective_date: computed property (athlete_moved_date ?? scheduled_date).
    - organization: not exposed (server-injected in perform_create).
    - validators = [] suppresses the auto-generated UniqueConstraint validator
      that would raise KeyError on PATCH. The model's full_clean() and the DB
      constraint remain the authoritative enforcement layer.
    - planned_workout: read-only nested representation with full blocks/intervals.
    """

    athlete_id = serializers.PrimaryKeyRelatedField(
        source="athlete",
        queryset=Athlete.objects.none(),
    )
    planned_workout_id = serializers.PrimaryKeyRelatedField(
        source="planned_workout",
        queryset=PlannedWorkout.objects.none(),
    )
    planned_workout_title = serializers.SerializerMethodField()
    planned_workout = PlannedWorkoutReadSerializer(read_only=True)
    assigned_by_id = serializers.PrimaryKeyRelatedField(
        source="assigned_by",
        read_only=True,
        allow_null=True,
    )
    effective_date = serializers.SerializerMethodField()

    # PR-145d: read-only computed fields
    compliance_color = serializers.CharField(read_only=True)
    weather_snapshot = serializers.JSONField(read_only=True)

    # PR-145g-fix: athlete display name
    athlete_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutAssignment
        fields = _ASSIGNMENT_FIELDS
        read_only_fields = [
            "id",
            "planned_workout_title",
            "planned_workout",
            "assigned_by_id",
            "snapshot_version",
            "compliance_color",
            "weather_snapshot",
            "coach_comment",
            "coach_commented_at",
            "athlete_name",
            "assigned_at",
            "updated_at",
            "effective_date",
        ]
        validators = []

    def get_planned_workout_title(self, obj):
        if obj.planned_workout_id is None:
            return None
        return obj.planned_workout.name

    def get_effective_date(self, obj):
        return obj.effective_date

    def get_athlete_name(self, obj):
        if obj.athlete_id is None:
            return ""
        user = obj.athlete.user
        name = f"{user.first_name} {user.last_name}".strip()
        return name or user.username or ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["athlete_id"].queryset = Athlete.objects.filter(
                organization=organization
            )
            self.fields["planned_workout_id"].queryset = PlannedWorkout.objects.filter(
                organization=organization
            )
        # PR-145f: scheduled_date is now writable on update for coaches (drag-to-move).
        # Athletes still cannot update it (enforced by WorkoutAssignmentAthleteSerializer).


class WorkoutAssignmentAthleteSerializer(serializers.ModelSerializer):
    """
    Athlete-write serializer for WorkoutAssignment.

    Writable by athlete: athlete_notes, athlete_moved_date, status.
    All other fields are read-only.
    organization is not exposed.
    planned_workout: read-only nested representation with full blocks/intervals.
    """

    athlete_id = serializers.PrimaryKeyRelatedField(
        source="athlete",
        read_only=True,
    )
    planned_workout_id = serializers.PrimaryKeyRelatedField(
        source="planned_workout",
        read_only=True,
    )
    planned_workout_title = serializers.SerializerMethodField()
    planned_workout = PlannedWorkoutReadSerializer(read_only=True)
    assigned_by_id = serializers.PrimaryKeyRelatedField(
        source="assigned_by",
        read_only=True,
        allow_null=True,
    )
    effective_date = serializers.SerializerMethodField()

    # PR-145d: athlete-writable execution fields
    actual_duration_seconds = serializers.IntegerField(required=False, allow_null=True)
    actual_distance_meters = serializers.IntegerField(required=False, allow_null=True)
    actual_elevation_gain = serializers.IntegerField(required=False, allow_null=True)
    rpe = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)

    # PR-145d: server-computed read-only fields
    compliance_color = serializers.CharField(read_only=True)
    weather_snapshot = serializers.JSONField(read_only=True)

    # PR-145g-fix: athlete display name
    athlete_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutAssignment
        fields = _ASSIGNMENT_FIELDS
        read_only_fields = [
            "id",
            "athlete_id",
            "planned_workout_id",
            "planned_workout_title",
            "planned_workout",
            "assigned_by_id",
            "scheduled_date",
            "day_order",
            "coach_notes",
            "target_zone_override",
            "target_pace_override",
            "target_rpe_override",
            "target_power_override",
            "snapshot_version",
            "compliance_color",
            "weather_snapshot",
            "coach_comment",
            "coach_commented_at",
            "athlete_name",
            "assigned_at",
            "updated_at",
            "effective_date",
        ]
        validators = []

    def get_planned_workout_title(self, obj):
        if obj.planned_workout_id is None:
            return None
        return obj.planned_workout.name

    def get_effective_date(self, obj):
        return obj.effective_date

    def get_athlete_name(self, obj):
        if obj.athlete_id is None:
            return ""
        user = obj.athlete.user
        name = f"{user.first_name} {user.last_name}".strip()
        return name or user.username or ""


# ==============================================================================
# PR-119: WorkoutReconciliation serializer
# ==============================================================================

_RECONCILIATION_FIELDS = [
    "id",
    "assignment_id",
    "completed_activity_id",
    "state",
    "match_method",
    "match_confidence",
    "compliance_score",
    "compliance_category",
    "primary_target_used",
    "score_detail",
    "signals",
    "reconciled_at",
    "notes",
    "created_at",
    "updated_at",
]


# ==============================================================================
# PR-X4: ExternalIdentity serializer
# ==============================================================================


class ExternalIdentitySerializer(serializers.ModelSerializer):
    """
    Serializer for ExternalIdentity.

    alumno_id queryset is scoped to alumnos owned by the authenticated coach
    (Alumno.entrenador == request.user). This prevents cross-coach FK injection
    at the serializer boundary.

    status and linked_at are computed by the ViewSet on create/update; they are
    never accepted from the client (read-only).

    validators = [] suppresses the conditional UniqueConstraint validator for
    (provider, alumno) which raises KeyError on PATCH when alumno is absent
    from the partial payload. DB integrity is the enforcement layer.
    """

    alumno_id = serializers.PrimaryKeyRelatedField(
        source="alumno",
        queryset=Alumno.objects.none(),  # overridden in __init__ from request.user
        allow_null=True,
        required=False,
    )

    class Meta:
        model = ExternalIdentity
        fields = [
            "id",
            "provider",
            "external_user_id",
            "alumno_id",
            "status",
            "linked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "linked_at", "created_at", "updated_at"]
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields["alumno_id"].queryset = Alumno.objects.filter(
                entrenador=request.user
            )


class WorkoutReconciliationSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for WorkoutReconciliation.

    All fields are read-only — state transitions happen exclusively via service
    function calls (reconcile, auto_match_and_reconcile, mark_assignment_missed).
    The client never writes to this model directly.

    organization is not exposed — it is always the URL-derived org.
    """

    assignment_id = serializers.PrimaryKeyRelatedField(
        source="assignment",
        read_only=True,
    )
    completed_activity_id = serializers.PrimaryKeyRelatedField(
        source="completed_activity",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = WorkoutReconciliation
        fields = _RECONCILIATION_FIELDS
        read_only_fields = _RECONCILIATION_FIELDS


# ==============================================================================
# PR-155: TrainingWeek serializer
# ==============================================================================

class TrainingWeekSerializer(serializers.ModelSerializer):
    """
    Serializer for TrainingWeek.

    organization and athlete are injected by the ViewSet — never client-supplied.
    week_start is validated as a Monday by the model's clean().
    """

    class Meta:
        model = TrainingWeek
        fields = [
            "id",
            "athlete",
            "week_start",
            "phase",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "organization", "created_at", "updated_at"]


class MacroRowSerializer(serializers.Serializer):
    """
    Read-only aggregated row for the MacroView table.

    One row per athlete, containing the athlete's phase for the requested
    week_start plus contextual data (goal A, injuries, wellness average).
    """
    athlete_id = serializers.IntegerField()
    athlete_name = serializers.CharField()
    phase = serializers.CharField(allow_null=True)
    notes = serializers.CharField(allow_null=True)
    training_week_id = serializers.IntegerField(allow_null=True)
    goal_a_title = serializers.CharField(allow_null=True)
    goal_a_priority = serializers.CharField(allow_null=True)
    goal_a_date = serializers.DateField(allow_null=True)
    days_until_race = serializers.IntegerField(allow_null=True)
    has_active_injury = serializers.BooleanField()
    wellness_avg = serializers.FloatField(allow_null=True)
    all_goals_brief = serializers.ListField(child=serializers.DictField(), default=list)
