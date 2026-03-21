# Generated for PR-130: Billing foundation — OrganizationSubscription model.
#
# atomic=False: mirrors the pattern from 0080.
# RunPython seeds all existing Organizations with plan='free'.

import django.db.models.deletion
from django.db import migrations, models


def seed_subscriptions(apps, schema_editor):
    Organization = apps.get_model("core", "Organization")
    OrganizationSubscription = apps.get_model("core", "OrganizationSubscription")
    for org in Organization.objects.all():
        OrganizationSubscription.objects.get_or_create(
            organization=org,
            defaults={"plan": "free", "is_active": True},
        )


def unseed_subscriptions(apps, schema_editor):
    OrganizationSubscription = apps.get_model("core", "OrganizationSubscription")
    OrganizationSubscription.objects.all().delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0080_completedactivity_org_fk_to_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("free", "Free"), ("starter", "Starter"), ("pro", "Pro"), ("enterprise", "Enterprise")], default="free", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("seats_limit", models.PositiveIntegerField(blank=True, help_text="Max athlete seats. NULL = unlimited.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="core.organization")),
            ],
            options={
                "verbose_name": "Organization Subscription",
            },
        ),
        migrations.RunPython(seed_subscriptions, unseed_subscriptions),
    ]
