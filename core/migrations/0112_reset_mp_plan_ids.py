"""
PR-167e: Reset mp_plan_id on all CoachPricingPlans.

MercadoPago does not allow updating payment_methods on an existing preapproval_plan.
Plans created before PR-167e restricted payment methods to credit/debit only,
blocking account_money (saldo MP) — used by ~95% of Argentine mobile users.

Setting mp_plan_id=None triggers lazy re-creation (with the new unrestricted config)
on the next athlete checkout. The orphaned MP plans have no active subscribers
(webhook was broken before PR-167d) and are harmless.
"""
from django.db import migrations


def reset_mp_plan_ids(apps, schema_editor):
    CoachPricingPlan = apps.get_model("core", "CoachPricingPlan")
    updated = CoachPricingPlan.objects.filter(
        mp_plan_id__isnull=False
    ).update(mp_plan_id=None)
    if updated:
        print(f"\n  PR-167e: reset mp_plan_id on {updated} CoachPricingPlan(s).")


def noop(apps, schema_editor):
    # Irreversible by design: the old MP plan IDs are gone from the DB.
    # The old plans remain orphaned in MP's side but have no active subscribers.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0111_password_reset_token"),
    ]

    operations = [
        migrations.RunPython(reset_mp_plan_ids, noop),
    ]
