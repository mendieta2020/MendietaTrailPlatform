"""
One-shot management command: cleanup_prelaunch
==============================================
Removes test users and their downstream data created during pre-launch dry-runs.

PRESERVES (never touched):
  - User(email=fernandorubenmedieta@gmail.com)
  - Organization "Mendieta Trail Training" (the single org)
  - Membership of Fernando as owner in that org
  - Athlete "Test Trail" (the Athlete whose user == Fernando)
  - Everything hanging from Fernando or Test Trail
  - CoachPricingPlan records
  - OrganizationSubscription
  - OrgOAuthCredential (MercadoPago)
  - Fernando's OAuthCredential(s) / ExternalIdentity

DELETES:
  - Every User except Fernando  (CASCADE takes Membership, Coach, Athlete,
    OAuthCredential, ExternalIdentity, CompletedActivity, etc.)
  - AthleteInvitation (org-scoped only, not user-FK'd — all are test data)
  - TeamInvitation (org-scoped only, not user-FK'd — all are test data)
  - OrganizationInviteLink (OneToOne with org — test data, regeneratable)

Usage:
  # Dry-run (default — lists what WOULD be deleted, touches nothing):
  python manage.py cleanup_prelaunch

  # Real delete (requires explicit flags):
  python manage.py cleanup_prelaunch --no-dry-run --force

POST-CLEANUP: Delete this file. It is a one-shot tool.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Athlete,
    AthleteInvitation,
    AthleteSubscription,
    Coach,
    Membership,
    Organization,
    OrganizationInviteLink,
    TeamInvitation,
)

FERNANDO_EMAIL = "fernandorubenmedieta@gmail.com"

User = get_user_model()


class Command(BaseCommand):
    help = "Pre-launch DB cleanup: remove test users/data, preserve Fernando + Test Trail."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-dry-run",
            action="store_true",
            default=False,
            help="Execute real deletes (default is dry-run only).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Required together with --no-dry-run to confirm destructive operation.",
        )

    def handle(self, *args, **options):
        dry_run = not options["no_dry_run"]
        force = options["force"]

        if not dry_run and not force:
            raise CommandError(
                "You must pass both --no-dry-run AND --force to execute real deletes."
            )

        mode = "DRY-RUN" if dry_run else "*** REAL DELETE ***"
        self.stdout.write(self.style.WARNING(f"\n=== cleanup_prelaunch [{mode}] ===\n"))

        # ------------------------------------------------------------------ #
        # 1. Resolve Fernando + org + anchors                                 #
        # ------------------------------------------------------------------ #
        try:
            fernando = User.objects.get(email=FERNANDO_EMAIL)
        except User.DoesNotExist:
            raise CommandError(f"ABORT: User '{FERNANDO_EMAIL}' not found. Wrong DB?")

        self.stdout.write(f"[PRESERVE] User: {fernando.email} (id={fernando.pk})")

        orgs = Organization.objects.all()
        if orgs.count() != 1:
            raise CommandError(
                f"ABORT: Expected exactly 1 Organization, found {orgs.count()}. "
                "Inspect manually."
            )
        org = orgs.first()
        self.stdout.write(f"[PRESERVE] Organization: '{org.name}' (id={org.pk})")

        # Fernando's Membership (owner)
        try:
            fernando_membership = Membership.objects.get(user=fernando, organization=org)
        except Membership.DoesNotExist:
            raise CommandError("ABORT: Fernando's Membership not found.")
        self.stdout.write(
            f"[PRESERVE] Membership: id={fernando_membership.pk} role={fernando_membership.role}"
        )

        # Fernando's Coach record
        try:
            fernando_coach = Coach.objects.get(user=fernando, organization=org)
            self.stdout.write(f"[PRESERVE] Coach: id={fernando_coach.pk}")
        except Coach.DoesNotExist:
            fernando_coach = None
            self.stdout.write("[INFO] No Coach record found for Fernando (may be normal).")

        # Test Trail: Athlete whose user == Fernando in this org
        test_trail_qs = Athlete.objects.filter(user=fernando, organization=org)
        if not test_trail_qs.exists():
            self.stdout.write(
                self.style.WARNING("[WARN] No Athlete linked to Fernando in this org (Test Trail not found).")
            )
            test_trail_athlete = None
        elif test_trail_qs.count() > 1:
            # Edge case: multiple athletes for Fernando — preserve all of them
            ids = list(test_trail_qs.values_list("pk", flat=True))
            self.stdout.write(
                self.style.WARNING(
                    f"[WARN] {test_trail_qs.count()} Athlete records for Fernando: ids={ids} — ALL preserved."
                )
            )
            test_trail_athlete = None  # signal: preserve all Fernando athletes
        else:
            test_trail_athlete = test_trail_qs.first()
            self.stdout.write(
                f"[PRESERVE] Athlete (Test Trail): id={test_trail_athlete.pk}"
            )

        self.stdout.write("")

        # ------------------------------------------------------------------ #
        # 2. Identify what will be deleted                                    #
        # ------------------------------------------------------------------ #

        # 2a. Users to delete
        users_to_delete = User.objects.exclude(pk=fernando.pk)
        user_count = users_to_delete.count()
        self.stdout.write(self.style.ERROR(f"[DELETE] Users to remove: {user_count}"))
        for u in users_to_delete.order_by("email"):
            self.stdout.write(f"         - id={u.pk}  email={u.email}  name={u.get_full_name()}")

        # 2b. Cascade counts (estimated — informational)
        other_memberships = Membership.objects.exclude(pk=fernando_membership.pk)
        other_athletes = (
            Athlete.objects.exclude(user=fernando)
            if test_trail_athlete is None
            else Athlete.objects.exclude(pk__in=test_trail_qs.values("pk"))
        )
        other_coaches = (
            Coach.objects.exclude(pk=fernando_coach.pk)
            if fernando_coach
            else Coach.objects.all()
        )
        other_subs = AthleteSubscription.objects.filter(athlete__in=other_athletes)

        self.stdout.write(f"  ↳ Memberships (cascade): {other_memberships.count()}")
        self.stdout.write(f"  ↳ Athletes   (cascade): {other_athletes.count()}")
        self.stdout.write(f"  ↳ Coaches    (cascade): {other_coaches.count()}")
        self.stdout.write(f"  ↳ AthleteSubscriptions (cascade from athletes): {other_subs.count()}")
        self.stdout.write("")

        # 2c. Non-user-FK'd records (explicit delete)
        athlete_invitations = AthleteInvitation.objects.all()
        team_invitations = TeamInvitation.objects.all()
        invite_links = OrganizationInviteLink.objects.all()

        self.stdout.write(
            self.style.ERROR(f"[DELETE] AthleteInvitation (all): {athlete_invitations.count()}")
        )
        for inv in athlete_invitations:
            self.stdout.write(f"         - id={inv.pk}  email={inv.email}  status={inv.status}")

        self.stdout.write(
            self.style.ERROR(f"[DELETE] TeamInvitation (all): {team_invitations.count()}")
        )
        for inv in team_invitations:
            self.stdout.write(f"         - id={inv.pk}  role={inv.role}  status={inv.status}")

        self.stdout.write(
            self.style.ERROR(f"[DELETE] OrganizationInviteLink (all): {invite_links.count()}")
        )
        for link in invite_links:
            self.stdout.write(f"         - id={link.pk}  slug={link.slug}  active={link.is_active}")

        self.stdout.write("")

        # ------------------------------------------------------------------ #
        # 3. Dry-run exit                                                     #
        # ------------------------------------------------------------------ #
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "DRY-RUN COMPLETE — nothing deleted.\n"
                    "Review the list above, then run:\n"
                    "  python manage.py cleanup_prelaunch --no-dry-run --force"
                )
            )
            return

        # ------------------------------------------------------------------ #
        # 4. Real delete (inside transaction)                                 #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Executing real deletes inside transaction.atomic()..."))

        with transaction.atomic():
            # 4a. Explicit deletes first (to avoid FK issues with SET_NULL refs)
            ai_deleted, _ = AthleteInvitation.objects.all().delete()
            self.stdout.write(f"  Deleted {ai_deleted} AthleteInvitation(s)")

            ti_deleted, _ = TeamInvitation.objects.all().delete()
            self.stdout.write(f"  Deleted {ti_deleted} TeamInvitation(s)")

            il_deleted, _ = OrganizationInviteLink.objects.all().delete()
            self.stdout.write(f"  Deleted {il_deleted} OrganizationInviteLink(s)")

            # 4b. Delete non-Fernando users (cascades Membership, Coach, Athlete,
            #     AthleteSubscription, OAuthCredential, ExternalIdentity, etc.)
            deleted_users = 0
            for user in users_to_delete:
                email = user.email
                user.delete()
                deleted_users += 1
                self.stdout.write(f"  Deleted User: {email}")

            self.stdout.write(f"\n  Total users deleted: {deleted_users}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== DELETE COMPLETE ==="))
        self.stdout.write("")

        # ------------------------------------------------------------------ #
        # 5. Post-delete verification counts                                  #
        # ------------------------------------------------------------------ #
        self.stdout.write("--- Post-cleanup verification ---")
        self.stdout.write(f"User.objects.count()                = {User.objects.count()}")
        first_user = User.objects.first()
        self.stdout.write(f"User.objects.first().email          = {first_user.email if first_user else 'NONE'}")
        self.stdout.write(f"Organization.objects.count()        = {Organization.objects.count()}")
        self.stdout.write(f"Membership.objects.count()          = {Membership.objects.count()}")
        self.stdout.write(f"Coach.objects.count()               = {Coach.objects.count()}")
        self.stdout.write(f"Athlete.objects.count()             = {Athlete.objects.count()}")
        self.stdout.write(f"AthleteSubscription.objects.count() = {AthleteSubscription.objects.count()}")
        self.stdout.write(f"AthleteInvitation.objects.count()   = {AthleteInvitation.objects.count()}")
        self.stdout.write(f"TeamInvitation.objects.count()      = {TeamInvitation.objects.count()}")
        self.stdout.write(f"OrganizationInviteLink.objects.count()= {OrganizationInviteLink.objects.count()}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING("ACTION REQUIRED: Delete this file after use (one-shot command).")
        )
