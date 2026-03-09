"""
core/serializers_p1.py

Serializers for the P1 organization-first domain: RaceEvent and AthleteGoal.

Design rules enforced here:
- organization is NEVER a client-controlled field; it is injected by the ViewSet.
- FK querysets (athlete, target_event) are scoped to the request organization via
  serializer context["organization"]. This is belt-and-suspenders: the model's
  clean() also enforces cross-org invariants.
- No depth > 0: related objects are exposed as PKs only.
- created_by is set by the ViewSet; not writable by the client.
"""

from rest_framework import serializers

from core.models import Athlete, AthleteGoal, RaceEvent


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
