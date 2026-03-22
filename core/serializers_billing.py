from rest_framework import serializers
from core.models import OrganizationSubscription, SubscriptionPlan


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
