"""
PR-149: Serializers for athlete registration and onboarding.

Three flows:
1. RegisterSerializer — email/password registration
2. GoogleAuthSerializer — Google ID-token verification
3. OnboardingCompleteSerializer — profile + availability + goal in one payload
"""

import uuid
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.models import AthleteInvitation, AthleteProfile

logger = logging.getLogger(__name__)
User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo electrónico."
            )
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        username = f"{email.split('@')[0]}_{uuid.uuid4().hex[:6]}"
        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        logger.info(
            "athlete_registered",
            extra={"user_id": user.id, "method": "email"},
        )
        return user


class GoogleAuthSerializer(serializers.Serializer):
    credential = serializers.CharField()


class AvailabilityEntrySerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    is_available = serializers.BooleanField()
    reason = serializers.CharField(
        max_length=100, required=False, default="", allow_blank=True,
    )
    preferred_time = serializers.ChoiceField(
        choices=[("", ""), *AthleteProfile.TrainingTime.choices],
        required=False,
        default="",
    )


class GoalSerializer(serializers.Serializer):
    race_name = serializers.CharField(max_length=300)
    race_date = serializers.DateField()
    distance_km = serializers.FloatField(required=False, allow_null=True)
    elevation_gain_m = serializers.FloatField(required=False, allow_null=True)
    priority = serializers.ChoiceField(
        choices=["A", "B", "C"], default="A",
    )


class OnboardingCompleteSerializer(serializers.Serializer):
    """
    Single-payload onboarding: profile + availability + optional goal.
    Organization is derived from the invitation token (never from client).
    """

    # Invitation context
    invitation_token = serializers.UUIDField()
    coach_plan_id = serializers.IntegerField(required=False, allow_null=True)

    # Required personal data
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    birth_date = serializers.DateField()
    weight_kg = serializers.FloatField()
    height_cm = serializers.FloatField()
    phone_number = serializers.CharField(max_length=20)

    # Availability (7 entries expected)
    availability = AvailabilityEntrySerializer(many=True)

    # Optional personal data
    gender = serializers.ChoiceField(
        choices=[("", ""), ("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")],
        required=False, default="",
    )
    province = serializers.CharField(max_length=120, required=False, default="", allow_blank=True)
    city = serializers.CharField(max_length=120, required=False, default="", allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, default="", allow_blank=True)
    instagram_handle = serializers.CharField(max_length=50, required=False, default="", allow_blank=True)
    profession = serializers.CharField(max_length=100, required=False, default="", allow_blank=True)
    blood_type = serializers.ChoiceField(
        choices=[("", ""), *AthleteProfile.BloodType.choices],
        required=False, default="",
    )
    clothing_size = serializers.ChoiceField(
        choices=[("", ""), *AthleteProfile.ClothingSize.choices],
        required=False, default="",
    )
    emergency_contact_name = serializers.CharField(
        max_length=100, required=False, default="", allow_blank=True,
    )
    emergency_contact_phone = serializers.CharField(
        max_length=20, required=False, default="", allow_blank=True,
    )

    # Optional athletic data
    training_age_years = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    pace_1000m_seconds = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    max_hr_bpm = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    resting_hr_bpm = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    vo2max = serializers.FloatField(required=False, allow_null=True)
    weekly_available_hours = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    preferred_training_time = serializers.ChoiceField(
        choices=[("", ""), *AthleteProfile.TrainingTime.choices],
        required=False, default="",
    )
    best_10k_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    best_21k_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )
    best_42k_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )

    # Female health (optional)
    menstrual_tracking_enabled = serializers.BooleanField(
        required=False, default=False,
    )
    menstrual_cycle_days = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
    )

    # Optional goal
    goal = GoalSerializer(required=False, allow_null=True)

    def validate_invitation_token(self, value):
        from django.utils import timezone

        try:
            invitation = AthleteInvitation.objects.select_related(
                "organization", "coach_plan",
            ).get(token=value)
        except AthleteInvitation.DoesNotExist:
            raise serializers.ValidationError("Invitación no encontrada.")

        if invitation.status == AthleteInvitation.Status.EXPIRED:
            raise serializers.ValidationError("Esta invitación ha expirado.")
        if invitation.status == AthleteInvitation.Status.ACCEPTED:
            raise serializers.ValidationError("Esta invitación ya fue aceptada.")
        if invitation.status == AthleteInvitation.Status.REJECTED:
            raise serializers.ValidationError("Esta invitación fue rechazada.")
        if invitation.expires_at and invitation.expires_at < timezone.now():
            invitation.status = AthleteInvitation.Status.EXPIRED
            invitation.save(update_fields=["status"])
            raise serializers.ValidationError("Esta invitación ha expirado.")

        self.context["invitation"] = invitation
        return value

    def validate(self, attrs):
        """Cross-field: if invitation has no coach_plan, coach_plan_id is required."""
        from core.models import CoachPricingPlan

        invitation = self.context.get("invitation")
        if invitation and not invitation.coach_plan_id:
            plan_id = attrs.get("coach_plan_id")
            if not plan_id:
                raise serializers.ValidationError({
                    "coach_plan_id": "Debes seleccionar un plan.",
                })
            try:
                plan = CoachPricingPlan.objects.get(
                    pk=plan_id,
                    organization=invitation.organization,
                    is_active=True,
                )
            except CoachPricingPlan.DoesNotExist:
                raise serializers.ValidationError({
                    "coach_plan_id": "Plan no válido.",
                })
            self.context["selected_plan"] = plan
        return attrs

    def validate_availability(self, value):
        if len(value) != 7:
            raise serializers.ValidationError(
                "Se requieren exactamente 7 entradas de disponibilidad (una por día)."
            )
        days_seen = {entry["day_of_week"] for entry in value}
        if len(days_seen) != 7 or days_seen != set(range(7)):
            raise serializers.ValidationError(
                "Cada día de la semana (0-6) debe aparecer exactamente una vez."
            )
        return value
