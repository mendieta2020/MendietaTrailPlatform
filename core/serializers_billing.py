from rest_framework import serializers
from core.models import OrganizationSubscription, SubscriptionPlan, AthleteInvitation


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "name", "plan_tier", "price_ars",
            "seats_included", "seats_extra_price_ars", "trial_days",
        ]


class BillingStatusSerializer(serializers.ModelSerializer):
    is_in_trial = serializers.SerializerMethodField()
    trial_days_remaining = serializers.SerializerMethodField()
    seats_used = serializers.SerializerMethodField()
    plan_display = serializers.CharField(source="get_plan_display", read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = [
            "plan", "plan_display", "is_active", "is_in_trial",
            "trial_days_remaining", "trial_ends_at",
            "seats_limit", "seats_used", "mp_preapproval_id",
            "is_managed_plan",
        ]

    def get_is_in_trial(self, obj):
        return obj.is_in_trial()

    def get_trial_days_remaining(self, obj):
        from django.utils import timezone
        if obj.trial_ends_at and obj.trial_ends_at > timezone.now():
            return (obj.trial_ends_at - timezone.now()).days
        return 0

    def get_seats_used(self, obj):
        from core.models import Athlete
        return Athlete.objects.filter(
            organization=obj.organization, is_active=True
        ).count()


# ==============================================================================
# PR-135: AthleteInvitation serializers
# ==============================================================================


class AthleteInvitationCreateSerializer(serializers.Serializer):
    """
    Input for POST /api/billing/invitations/
    Coach creates an invitation for an athlete.
    """
    coach_plan = serializers.PrimaryKeyRelatedField(
        queryset=lambda: __import__('core.models', fromlist=['CoachPricingPlan']).CoachPricingPlan.objects.all()
    )
    email = serializers.EmailField()

    def __init__(self, *args, **kwargs):
        from core.models import CoachPricingPlan
        super().__init__(*args, **kwargs)
        self.fields['coach_plan'].queryset = CoachPricingPlan.objects.all()

    def validate_coach_plan(self, plan):
        request = self.context.get("request")
        org = getattr(request, "auth_organization", None) if request else None
        if org is None:
            raise serializers.ValidationError("No organization context.")
        if plan.organization_id != org.pk:
            raise serializers.ValidationError(
                "El plan no pertenece a tu organización."
            )
        return plan


class _CoachPlanSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price_ars = serializers.DecimalField(max_digits=10, decimal_places=2)


class AthleteInvitationDetailSerializer(serializers.ModelSerializer):
    """
    Read-only, public — used in InvitationDetailView (AllowAny).
    """
    coach_plan = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = AthleteInvitation
        fields = [
            "token", "email", "status",
            "coach_plan", "organization_name",
            "expires_at", "is_expired",
        ]

    def get_coach_plan(self, obj):
        return {
            "id": obj.coach_plan_id,
            "name": obj.coach_plan.name,
            "price_ars": str(obj.coach_plan.price_ars),
        }

    def get_is_expired(self, obj):
        return obj.is_expired()


class AthleteInvitationAcceptSerializer(serializers.Serializer):
    """
    Optional input for POST /api/billing/invitations/<token>/accept/
    mp_preapproval_id may arrive from an MP redirect.
    """
    mp_preapproval_id = serializers.CharField(required=False, allow_blank=True)
