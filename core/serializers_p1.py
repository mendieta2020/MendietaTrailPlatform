"""
core/serializers_p1.py

Serializers for the P1 organization-first domain: RaceEvent, AthleteGoal,
and AthleteProfile.

Design rules enforced here:
- organization is NEVER a client-controlled field; it is injected by the ViewSet.
- FK querysets are scoped to the request organization via serializer
  context["organization"]. The model's clean() provides a second enforcement layer.
- No depth > 0: related objects are exposed as PKs only.
- created_by / updated_by are set by the ViewSet; not writable by the client.
"""

from rest_framework import serializers

from core.models import Athlete, AthleteGoal, AthleteProfile, RaceEvent


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
