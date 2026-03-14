"""
core/serializers_p1_roster.py

Serializers for the P1 Roster API: Coach, Athlete (roster), Team,
Membership, and AthleteCoachAssignment.

Design rules enforced here:
- organization is NEVER a client-controlled field; it is injected by the ViewSet.
- FK querysets for roster FKs (coach_id, team_id) are scoped to
  context["organization"] to prevent cross-org writes at the serializer layer.
- user_id is writable on create (owner/coach specifies which user gets the role),
  read-only on update (a record's user cannot be reassigned after creation).
- No field list uses "__all__".
- assigned_by_id / created_by_id fields are always read-only (set by the ViewSet).
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.models import Athlete, AthleteCoachAssignment, Coach, Membership, Team

User = get_user_model()


class CoachSerializer(serializers.ModelSerializer):
    """
    Serializer for Coach.

    user_id is writable on create (owner assigns a User to the coach role)
    and read-only on update (a Coach record cannot be reassigned to a different user).
    organization is not exposed — injected by CoachViewSet in perform_create.
    """

    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
    )

    class Meta:
        model = Coach
        fields = [
            "id",
            "user_id",
            "bio",
            "certifications",
            "specialties",
            "years_experience",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # User cannot be reassigned after the Coach record is created.
        if self.instance is not None:
            self.fields["user_id"].read_only = True
            self.fields["user_id"].required = False


class AthleteRosterSerializer(serializers.ModelSerializer):
    """
    Serializer for Athlete (roster view).

    user_id is writable on create, read-only on update.
    coach_id and team_id querysets are scoped to context["organization"]
    to prevent cross-org FK writes at the serializer layer.
    organization is not exposed — injected by AthleteRosterViewSet.
    """

    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
    )
    coach_id = serializers.PrimaryKeyRelatedField(
        source="coach",
        queryset=Coach.objects.none(),
        allow_null=True,
        required=False,
    )
    team_id = serializers.PrimaryKeyRelatedField(
        source="team",
        queryset=Team.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Athlete
        fields = [
            "id",
            "user_id",
            "coach_id",
            "team_id",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # Suppress auto-generated UniqueConstraint validator for PATCH.
        # The model full_clean() and DB constraint remain the authoritative layer.
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # User cannot be reassigned after the Athlete record is created.
        if self.instance is not None:
            self.fields["user_id"].read_only = True
            self.fields["user_id"].required = False
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["coach_id"].queryset = Coach.objects.filter(
                organization=organization
            )
            self.fields["team_id"].queryset = Team.objects.filter(
                organization=organization
            )


class TeamSerializer(serializers.ModelSerializer):
    """
    Serializer for Team.

    organization is not exposed — injected by TeamViewSet.
    Explicit duplicate-name validation checks uniqueness within the org
    because organization is excluded from the fields list (no auto UniqueTogetherValidator).
    """

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        organization = self.context.get("organization")
        if organization is not None:
            name = attrs.get("name", getattr(self.instance, "name", None))
            if name:
                qs = Team.objects.filter(organization=organization, name=name)
                if self.instance is not None:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise serializers.ValidationError(
                        {"name": "A team with this name already exists in this organization."}
                    )
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for Membership.

    user_id is writable on create (owner adds a User to the org),
    read-only on update (membership cannot be reassigned to a different user).
    team_id queryset is scoped to context["organization"].
    organization is not exposed — injected by MembershipViewSet.
    """

    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
    )
    team_id = serializers.PrimaryKeyRelatedField(
        source="team",
        queryset=Team.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Membership
        fields = [
            "id",
            "user_id",
            "role",
            "staff_title",
            "team_id",
            "is_active",
            "joined_at",
            "left_at",
        ]
        read_only_fields = ["id", "joined_at"]
        # Suppress auto-generated UniqueConstraint validator for PATCH.
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # User cannot be changed after the Membership record is created.
        if self.instance is not None:
            self.fields["user_id"].read_only = True
            self.fields["user_id"].required = False
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["team_id"].queryset = Team.objects.filter(
                organization=organization
            )


class AthleteCoachAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for AthleteCoachAssignment.

    athlete_id and coach_id querysets are scoped to context["organization"]
    to prevent cross-org FK writes at the serializer layer.
    assigned_by_id is read-only — set by the ViewSet in create().
    organization is not exposed — injected by AthleteCoachAssignmentViewSet.

    All fields except athlete_id, coach_id, and role are read-only.
    ended_at is managed exclusively via the `end` action; it is never
    accepted from the client.
    """

    athlete_id = serializers.PrimaryKeyRelatedField(
        source="athlete",
        queryset=Athlete.objects.none(),
    )
    coach_id = serializers.PrimaryKeyRelatedField(
        source="coach",
        queryset=Coach.objects.none(),
    )
    assigned_by_id = serializers.PrimaryKeyRelatedField(
        source="assigned_by",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AthleteCoachAssignment
        fields = [
            "id",
            "athlete_id",
            "coach_id",
            "role",
            "assigned_by_id",
            "assigned_at",
            "ended_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "assigned_by_id",
            "assigned_at",
            "ended_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context.get("organization")
        if organization is not None:
            self.fields["athlete_id"].queryset = Athlete.objects.filter(
                organization=organization
            )
            self.fields["coach_id"].queryset = Coach.objects.filter(
                organization=organization
            )
