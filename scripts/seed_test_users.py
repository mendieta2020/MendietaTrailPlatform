"""
Seed script for PR-167c local testing.
Run with: python manage.py shell < scripts/seed_test_users.py
Or:        python manage.py shell -c "$(cat scripts/seed_test_users.py)"

Idempotent — safe to run multiple times.
Credentials: owner@test.com / coach@test.com / atleta1@test.com / atleta2@test.com
Password: test1234
"""

from django.contrib.auth.models import User
from core.models import Organization, Membership, Athlete, Coach, CoachPricingPlan, AthleteSubscription
from django.utils import timezone
from datetime import timedelta

# Org
org, created = Organization.objects.get_or_create(id=1, defaults={"name": "Mendieta Trail Training"})
print(f"[org]   {'created' if created else 'exists'}: {org.name}")

# Owner
owner, created = User.objects.get_or_create(username="owner", defaults={"email": "owner@test.com", "first_name": "Fernando", "last_name": "Mendieta"})
owner.set_password("test1234")
owner.is_superuser = True
owner.is_staff = True
owner.save()
Membership.objects.get_or_create(user=owner, organization=org, defaults={"role": "owner"})
print(f"[owner] {'created' if created else 'exists'}: owner@test.com")

# Coach
coach_user, created = User.objects.get_or_create(username="coach", defaults={"email": "coach@test.com", "first_name": "Martin", "last_name": "Lopez"})
coach_user.set_password("test1234")
coach_user.save()
Membership.objects.get_or_create(user=coach_user, organization=org, defaults={"role": "coach"})
coach, _ = Coach.objects.get_or_create(user=coach_user, organization=org)
print(f"[coach] {'created' if created else 'exists'}: coach@test.com")

# Pricing plan
plan, created = CoachPricingPlan.objects.get_or_create(
    name="Test Plan",
    organization=org,
    defaults={"price_ars": 100, "is_active": True},
)
print(f"[plan]  {'created' if created else 'exists'}: {plan.name}")

# Athlete 1 — active subscription
a1_user, created = User.objects.get_or_create(username="atleta1", defaults={"email": "atleta1@test.com", "first_name": "Natalia", "last_name": "Moreno"})
a1_user.set_password("test1234")
a1_user.save()
Membership.objects.get_or_create(user=a1_user, organization=org, defaults={"role": "athlete"})
a1, _ = Athlete.objects.get_or_create(user=a1_user, organization=org, defaults={"coach": coach})
sub1, sub1_created = AthleteSubscription.objects.get_or_create(
    athlete=a1,
    coach_plan=plan,
    defaults={
        "organization": org,
        "status": "active",
        "last_payment_at": timezone.now(),
        "next_payment_at": timezone.now() + timedelta(days=30),
    },
)
print(f"[a1]    {'created' if created else 'exists'}: atleta1@test.com — sub status={sub1.status}")

# Athlete 2 — pending/trial
a2_user, created = User.objects.get_or_create(username="atleta2", defaults={"email": "atleta2@test.com", "first_name": "Tomas", "last_name": "Garcia"})
a2_user.set_password("test1234")
a2_user.save()
Membership.objects.get_or_create(user=a2_user, organization=org, defaults={"role": "athlete"})
a2, _ = Athlete.objects.get_or_create(user=a2_user, organization=org, defaults={"coach": coach})
sub2, sub2_created = AthleteSubscription.objects.get_or_create(
    athlete=a2,
    coach_plan=plan,
    defaults={
        "organization": org,
        "status": "pending",
        "trial_ends_at": timezone.now() + timedelta(days=7),
    },
)
print(f"[a2]    {'created' if created else 'exists'}: atleta2@test.com — sub status={sub2.status}")

print("\nDone.")
print("  owner@test.com   / test1234  (superuser)")
print("  coach@test.com   / test1234")
print("  atleta1@test.com / test1234  (sub: active)")
print("  atleta2@test.com / test1234  (sub: pending/trial)")
