"""
core/management/commands/backfill_alumnos_to_athletes.py

PR-124: Backfill legacy Alumno records into P1 Athlete/Membership roster.

Idempotent: safe to run multiple times; second run is a noop (get_or_create).
Additive-only: does not modify or delete Alumno records.
Fail-closed: --org-id must resolve an existing Organization; missing = CommandError.

Usage:
    python manage.py backfill_alumnos_to_athletes --org-id 1 --coach-user-id 3
    python manage.py backfill_alumnos_to_athletes --org-id 1 --coach-user-id 3 --dry-run
    python manage.py backfill_alumnos_to_athletes --org-id 1 --coach-user-id 3 --alumno-id 42

User resolution cascade (fail-closed, no placeholder users created):
    1. alumno.usuario        — direct FK
    2. email exact match     — User.email == alumno.email (unique result only)
    3. name exact match      — first_name/last_name (unique result only)
    4. SKIP with reason_code — no ambiguous or unresolvable records are written

Team resolution (non-blocking):
    Maps alumno.equipo.nombre -> Team(organization, name).
    If Team not found: Athlete created with team=None. Backfill is not blocked.

Rollback (if needed):
    Athlete.objects.filter(notes__startswith="backfill:alumno:").delete()
    Memberships created for athletes can be identified by checking Athlete records above.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Athlete, Coach, Membership, Organization, Team

User = get_user_model()
logger = logging.getLogger(__name__)

# Outcome codes (used in output and counters)
CREATED = "CREATED"
EXISTS = "EXISTS"
SKIP_NO_IDENTIFIER = "SKIP_NO_IDENTIFIER"
SKIP_EMAIL_AMBIGUOUS = "SKIP_EMAIL_AMBIGUOUS"
SKIP_NAME_AMBIGUOUS = "SKIP_NAME_AMBIGUOUS"
SKIP_MEMBERSHIP_CONFLICT = "SKIP_MEMBERSHIP_CONFLICT"
FAILED = "FAILED"

_SKIP_CODES = {
    SKIP_NO_IDENTIFIER,
    SKIP_EMAIL_AMBIGUOUS,
    SKIP_NAME_AMBIGUOUS,
    SKIP_MEMBERSHIP_CONFLICT,
}

_ALL_CODES = [CREATED, EXISTS, SKIP_NO_IDENTIFIER, SKIP_EMAIL_AMBIGUOUS,
              SKIP_NAME_AMBIGUOUS, SKIP_MEMBERSHIP_CONFLICT, FAILED]


class Command(BaseCommand):
    help = (
        "PR-124: Backfill legacy Alumno records into P1 Athlete/Membership roster. "
        "Idempotent and additive-only. Does not modify Alumno records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=int,
            required=True,
            help="ID of the existing Organization to backfill into.",
        )
        parser.add_argument(
            "--coach-user-id",
            type=int,
            required=True,
            help="User ID of the coach to ensure as a Coach record in the org.",
        )
        parser.add_argument(
            "--alumno-id",
            type=int,
            default=None,
            help="Process a single Alumno by ID (omit to process all).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate without writing to the database.",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            default=False,
            help="Abort on the first FAILED row instead of continuing.",
        )

    def handle(self, *args, **options):
        # Local import: Alumno is a legacy model; kept separate from P1 imports.
        from core.models import Alumno

        org_id = options["org_id"]
        coach_user_id = options["coach_user_id"]
        alumno_id = options.get("alumno_id")
        dry_run = options["dry_run"]
        fail_fast = options["fail_fast"]

        # ── 1. Resolve Organization (fail-closed) ──────────────────────────────
        try:
            organization = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization id={org_id} does not exist.")

        # ── 2. Resolve coach User ──────────────────────────────────────────────
        try:
            coach_user = User.objects.get(pk=coach_user_id)
        except User.DoesNotExist:
            raise CommandError(f"User id={coach_user_id} does not exist.")

        # ── 3. Ensure Coach + Membership(coach) in org ─────────────────────────
        coach = self._ensure_coach(coach_user, organization, dry_run)

        # ── 4. Build Alumno queryset ───────────────────────────────────────────
        qs = (
            Alumno.objects
            .select_related("usuario", "entrenador", "equipo")
            .order_by("id")
        )
        if alumno_id is not None:
            qs = qs.filter(pk=alumno_id)

        alumnos = list(qs)
        if not alumnos:
            self.stdout.write(
                self.style.WARNING("No Alumno records found for the given filters.")
            )
            return

        # ── 5. Process each Alumno ─────────────────────────────────────────────
        counters = {code: 0 for code in _ALL_CODES}

        for alumno in alumnos:
            outcome, detail = self._process_alumno(alumno, organization, coach, dry_run)
            counters[outcome] += 1
            self._log_row(alumno, outcome, detail, dry_run)
            if outcome == FAILED and fail_fast:
                raise CommandError(
                    f"--fail-fast: aborting after alumno_id={alumno.pk} | {detail}"
                )

        # ── 6. Summary ─────────────────────────────────────────────────────────
        dry_label = " [DRY RUN]" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\nBackfill complete{dry_label}. "
                f"Total={len(alumnos)} | "
                f"Created={counters[CREATED]} | "
                f"Exists={counters[EXISTS]} | "
                f"Skip(no_id)={counters[SKIP_NO_IDENTIFIER]} | "
                f"Skip(email_ambig)={counters[SKIP_EMAIL_AMBIGUOUS]} | "
                f"Skip(name_ambig)={counters[SKIP_NAME_AMBIGUOUS]} | "
                f"Skip(membership_conflict)={counters[SKIP_MEMBERSHIP_CONFLICT]} | "
                f"Failed={counters[FAILED]}"
            )
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _ensure_coach(self, coach_user, organization, dry_run):
        """
        get_or_create Coach + Membership(coach) for the given user+org.

        In dry-run mode, returns the existing Coach if found, or a transient
        unsaved instance. Either way, _process_alumno skips writes in dry-run.
        """
        existing = Coach.objects.filter(user=coach_user, organization=organization).first()
        if dry_run:
            return existing or Coach(user=coach_user, organization=organization)

        coach, coach_created = Coach.objects.get_or_create(
            user=coach_user,
            organization=organization,
        )
        Membership.objects.get_or_create(
            user=coach_user,
            organization=organization,
            defaults={"role": Membership.Role.COACH, "is_active": True},
        )
        if coach_created:
            logger.info(
                "backfill.coach_created",
                extra={"user_id": coach_user.pk, "org_id": organization.pk},
            )
        return coach

    def _resolve_user(self, alumno):
        """
        Fail-closed User resolution cascade.

        Returns (user_or_None, reason_code_str).
        reason_code_str is one of: "direct_link", "email_match", "name_match",
        SKIP_EMAIL_AMBIGUOUS, SKIP_NAME_AMBIGUOUS, SKIP_NO_IDENTIFIER.
        """
        # Step 1: direct FK
        if alumno.usuario_id:
            return alumno.usuario, "direct_link"

        # Step 2: exact email match (unique only)
        if alumno.email:
            matches = User.objects.filter(email__iexact=alumno.email)
            count = matches.count()
            if count == 1:
                return matches.first(), "email_match"
            if count > 1:
                return None, SKIP_EMAIL_AMBIGUOUS
            # count == 0: fall through to name match

        # Step 3: exact name match (unique only)
        if alumno.nombre and alumno.apellido:
            matches = User.objects.filter(
                first_name__iexact=alumno.nombre,
                last_name__iexact=alumno.apellido,
            )
            count = matches.count()
            if count == 1:
                return matches.first(), "name_match"
            if count > 1:
                return None, SKIP_NAME_AMBIGUOUS

        return None, SKIP_NO_IDENTIFIER

    def _resolve_team(self, alumno, organization):
        """
        Optional Team resolution. Returns Team or None (non-blocking).

        Maps alumno.equipo.nombre -> Team(organization, name).
        If the Team does not exist in P1, the Athlete is created without a team.
        """
        if not alumno.equipo_id:
            return None
        return Team.objects.filter(
            organization=organization,
            name=alumno.equipo.nombre,
        ).first()

    def _process_alumno(self, alumno, organization, coach, dry_run):
        """
        Process one Alumno. Returns (outcome_code, detail_str).

        Each Alumno is processed in its own savepoint so a single failure
        does not abort the full run.
        """
        try:
            user, resolution = self._resolve_user(alumno)

            if user is None:
                return resolution, f"alumno_id={alumno.pk} email={alumno.email!r}"

            # Check Membership conflict before writing anything
            existing_membership = Membership.objects.filter(
                user=user,
                organization=organization,
                is_active=True,
            ).first()
            if existing_membership and existing_membership.role != Membership.Role.ATHLETE:
                return (
                    SKIP_MEMBERSHIP_CONFLICT,
                    f"alumno_id={alumno.pk} existing_role={existing_membership.role}",
                )

            team = self._resolve_team(alumno, organization)

            # Dry-run: report what would happen without writing
            if dry_run:
                athlete_exists = Athlete.objects.filter(
                    user=user, organization=organization, is_active=True
                ).exists()
                return (
                    EXISTS if athlete_exists else CREATED,
                    f"dry_run resolution={resolution}",
                )

            with transaction.atomic():
                athlete, created = Athlete.objects.get_or_create(
                    user=user,
                    organization=organization,
                    defaults={
                        "coach": coach if coach.pk else None,
                        "team": team,
                        "is_active": True,
                        "notes": f"backfill:alumno:{alumno.pk}",
                    },
                )
                Membership.objects.get_or_create(
                    user=user,
                    organization=organization,
                    defaults={"role": Membership.Role.ATHLETE, "is_active": True},
                )

            return (
                CREATED if created else EXISTS,
                f"resolution={resolution} athlete_id={athlete.pk}",
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "backfill.alumno_failed",
                extra={"alumno_id": alumno.pk, "error": str(exc)},
            )
            return FAILED, str(exc)

    def _log_row(self, alumno, outcome, detail, dry_run):
        """Emit one structured output line per Alumno."""
        dry_label = "[DRY RUN] " if dry_run else ""
        line = (
            f"{dry_label}{outcome} | alumno_id={alumno.pk} "
            f"nombre={alumno.nombre!r} | {detail}"
        )
        if outcome == CREATED:
            self.stdout.write(self.style.SUCCESS(line))
        elif outcome in _SKIP_CODES or outcome == FAILED:
            self.stdout.write(self.style.WARNING(line))
        else:
            self.stdout.write(line)
