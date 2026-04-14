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

from core.models import Athlete, AthleteCoachAssignment, Coach, Membership, OAuthIntegrationStatus, Team, TeamInvitation

User = get_user_model()


class CoachSerializer(serializers.ModelSerializer):
    """
    Serializer for Coach.

    user_id is writable on create (owner assigns a User to the coach role)
    and read-only on update (a Coach record cannot be reassigned to a different user).
    organization is not exposed — injected by CoachViewSet in perform_create.

    first_name / last_name / email / username are read-only, derived from coach.user.
    """

    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
    )
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()

    def get_first_name(self, obj):
        return obj.user.first_name if obj.user_id else ""

    def get_last_name(self, obj):
        return obj.user.last_name if obj.user_id else ""

    def get_email(self, obj):
        return obj.user.email if obj.user_id else ""

    def get_username(self, obj):
        return obj.user.username if obj.user_id else ""

    class Meta:
        model = Coach
        fields = [
            "id",
            "user_id",
            "first_name",
            "last_name",
            "email",
            "username",
            "bio",
            "certifications",
            "specialties",
            "years_experience",
            "phone",
            "birth_date",
            "photo_url",
            "instagram",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "first_name", "last_name", "email", "username", "created_at", "updated_at"]

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
    first_name / last_name are read-only, derived from athlete.user.
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
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    coach_name = serializers.SerializerMethodField()
    devices = serializers.SerializerMethodField()
    membership_id = serializers.SerializerMethodField()

    def get_first_name(self, obj):
        return obj.user.first_name if obj.user_id else ""

    def get_last_name(self, obj):
        return obj.user.last_name if obj.user_id else ""

    def get_email(self, obj):
        return obj.user.email if obj.user_id else ""

    def get_coach_name(self, obj):
        """BUG-13 fix: return coach's full name so the UI doesn't fall back to 'Coach #N'."""
        if not obj.coach_id:
            return None
        try:
            u = obj.coach.user
            name = f"{u.first_name} {u.last_name}".strip()
            return name or u.email or None
        except Exception:
            return None

    def get_devices(self, obj):
        """Return up to 2 connected providers for this athlete (org-scoped via alumno)."""
        if not obj.user_id:
            return []
        connected = (
            OAuthIntegrationStatus.objects
            .filter(alumno__usuario=obj.user, connected=True)
            .values("provider", "connected", "created_at")
            .order_by("provider")[:2]
        )
        return [
            {
                "provider": d["provider"],
                "connected": True,
                "connected_at": d["created_at"].isoformat() if d["created_at"] else None,
            }
            for d in connected
        ]

    def get_membership_id(self, obj):
        """Return the active athlete Membership PK for this athlete in this org."""
        if not obj.user_id:
            return None
        membership = (
            Membership.objects
            .filter(
                user=obj.user,
                organization=obj.organization,
                role=Membership.Role.ATHLETE,
                is_active=True,
            )
            .values_list("id", flat=True)
            .first()
        )
        return membership

    class Meta:
        model = Athlete
        fields = [
            "id",
            "user_id",
            "first_name",
            "last_name",
            "email",
            "coach_id",
            "coach_name",
            "team_id",
            "notes",
            "is_active",
            "devices",
            "membership_id",
            # PR-145d: location for weather forecast
            "location_city",
            "location_lat",
            "location_lon",
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


# ==============================================================================
# PR-165a: TeamInvitation serializers
# ==============================================================================

_FORBIDDEN_INVITE_ROLES = {"owner", "athlete"}


class TeamInvitationSerializer(serializers.ModelSerializer):
    """Read serializer for TeamInvitation list/retrieve."""

    accepted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TeamInvitation
        fields = [
            "id",
            "token",
            "role",
            "email",
            "status",
            "created_at",
            "expires_at",
            "accepted_by_name",
        ]

    def get_accepted_by_name(self, obj):
        if obj.accepted_by:
            return obj.accepted_by.get_full_name() or obj.accepted_by.username
        return None


class TeamInvitationCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating a TeamInvitation."""

    class Meta:
        model = TeamInvitation
        fields = ["role", "email"]

    def validate_role(self, value):
        if value in _FORBIDDEN_INVITE_ROLES:
            raise serializers.ValidationError(
                f"No se puede invitar con el rol '{value}'."
            )
        return value

    def create(self, validated_data):
        from django.utils import timezone
        from datetime import timedelta

        request = self.context["request"]
        organization = self.context["organization"]
        validated_data["organization"] = organization
        validated_data["created_by"] = request.user
        validated_data["expires_at"] = timezone.now() + timedelta(days=7)
        return super().create(validated_data)
