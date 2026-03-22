"""
core/tests_pr124_backfill_alumnos.py

PR-124: Test suite for backfill_alumnos_to_athletes management command.

Coverage:
  - Happy path: creates Athlete + Membership(athlete)
  - Idempotency: second run is a noop
  - Coach: Coach record + Membership(coach) created in org
  - User resolution cascade: direct_link, email_match, name_match
  - User resolution SKIP: email_ambiguous, name_ambiguous, no_identifier
  - Membership conflict: existing non-athlete membership blocks Athlete creation
  - Team: resolved if P1 Team exists; None (non-blocking) if not
  - Dry-run: zero DB writes, output labelled [DRY RUN]
  - Single --alumno-id filter
  - Org/User not found: CommandError
  - Tenancy: Athlete scoped to correct org only
  - Athlete.notes traces source alumno_id
"""
import pytest
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Alumno, Athlete, Coach, Equipo, Membership, Organization, Team

User = get_user_model()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _org(slug="test-org"):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username, email="", first_name="", last_name=""):
    return User.objects.create_user(
        username=username,
        password="x",
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


def _alumno(entrenador, nombre="Ana", apellido="Garcia", usuario=None, email=None, equipo=None):
    return Alumno.objects.create(
        entrenador=entrenador,
        nombre=nombre,
        apellido=apellido,
        usuario=usuario,
        email=email,
        equipo=equipo,
    )


def _run(org_id, coach_user_id, **kwargs):
    """Call the command and return stdout as a string."""
    out = StringIO()
    call_command(
        "backfill_alumnos_to_athletes",
        org_id=org_id,
        coach_user_id=coach_user_id,
        stdout=out,
        **kwargs,
    )
    return out.getvalue()


# ── Test class ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBackfillAlumnosToAthletes:

    def setup_method(self):
        self.org = _org("trail-org")
        self.coach_user = _user("coach1", email="coach@trail.org")
        self.athlete_user = _user("athlete1", email="athlete@trail.org")

    # ── 1. Happy path ──────────────────────────────────────────────────────────

    def test_creates_athlete_and_membership(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        out = _run(self.org.pk, self.coach_user.pk)

        assert Athlete.objects.filter(
            user=self.athlete_user, organization=self.org
        ).exists()
        membership = Membership.objects.get(user=self.athlete_user, organization=self.org)
        assert membership.role == Membership.Role.ATHLETE
        assert "CREATED" in out

    # ── 2. Idempotency ─────────────────────────────────────────────────────────

    def test_idempotent_second_run(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)
        _run(self.org.pk, self.coach_user.pk)

        assert Athlete.objects.filter(
            user=self.athlete_user, organization=self.org
        ).count() == 1
        assert Membership.objects.filter(
            user=self.athlete_user, organization=self.org
        ).count() == 1

    def test_second_run_shows_exists(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)
        out = _run(self.org.pk, self.coach_user.pk)

        assert "EXISTS" in out

    # ── 3. Coach setup ─────────────────────────────────────────────────────────

    def test_coach_created_in_org(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)

        assert Coach.objects.filter(
            user=self.coach_user, organization=self.org
        ).exists()

    def test_coach_membership_created_with_coach_role(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)

        membership = Membership.objects.get(user=self.coach_user, organization=self.org)
        assert membership.role == Membership.Role.COACH

    def test_coach_idempotent(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)
        _run(self.org.pk, self.coach_user.pk)

        assert Coach.objects.filter(
            user=self.coach_user, organization=self.org
        ).count() == 1

    # ── 4. Org / User not found ────────────────────────────────────────────────

    def test_org_not_found_raises_command_error(self):
        with pytest.raises(CommandError, match="Organization"):
            _run(99999, self.coach_user.pk)

    def test_coach_user_not_found_raises_command_error(self):
        with pytest.raises(CommandError, match="User"):
            _run(self.org.pk, 99999)

    # ── 5. Dry-run ─────────────────────────────────────────────────────────────

    def test_dry_run_writes_no_athlete(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk, dry_run=True)

        assert not Athlete.objects.filter(
            user=self.athlete_user, organization=self.org
        ).exists()

    def test_dry_run_writes_no_membership(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk, dry_run=True)

        assert not Membership.objects.filter(
            user=self.athlete_user, organization=self.org, role="athlete"
        ).exists()

    def test_dry_run_output_labelled(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        out = _run(self.org.pk, self.coach_user.pk, dry_run=True)

        assert "DRY RUN" in out

    def test_dry_run_shows_created_for_new_athlete(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        out = _run(self.org.pk, self.coach_user.pk, dry_run=True)

        assert "CREATED" in out

    def test_dry_run_shows_exists_for_already_created(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)  # real run first
        out = _run(self.org.pk, self.coach_user.pk, dry_run=True)

        assert "EXISTS" in out

    # ── 6. Athlete.notes traces source ────────────────────────────────────────

    def test_athlete_notes_trace_alumno_id(self):
        alumno = _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)

        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        assert f"backfill:alumno:{alumno.pk}" in athlete.notes

    # ── 7. User resolution: email match ───────────────────────────────────────

    def test_user_resolved_by_email_match(self):
        user_with_email = _user("emailmatch", email="match@trail.org")
        _alumno(self.coach_user, usuario=None, email="match@trail.org")
        _run(self.org.pk, self.coach_user.pk)

        assert Athlete.objects.filter(
            user=user_with_email, organization=self.org
        ).exists()

    def test_skip_email_ambiguous(self):
        _user("dup_a", email="dup@trail.org")
        _user("dup_b", email="dup@trail.org")
        _alumno(self.coach_user, usuario=None, email="dup@trail.org")
        out = _run(self.org.pk, self.coach_user.pk)

        assert "SKIP_EMAIL_AMBIGUOUS" in out
        # No athlete should have been created for the ambiguous-email users
        dup_users = User.objects.filter(email="dup@trail.org")
        assert not Athlete.objects.filter(
            user__in=dup_users, organization=self.org
        ).exists()

    # ── 8. User resolution: name match ────────────────────────────────────────

    def test_user_resolved_by_name_match(self):
        user_named = _user("named1", first_name="Carlos", last_name="Lopez")
        _alumno(self.coach_user, nombre="Carlos", apellido="Lopez", usuario=None)
        _run(self.org.pk, self.coach_user.pk)

        assert Athlete.objects.filter(
            user=user_named, organization=self.org
        ).exists()

    def test_skip_name_ambiguous(self):
        _user("named_a", first_name="Laura", last_name="Perez")
        _user("named_b", first_name="Laura", last_name="Perez")
        _alumno(self.coach_user, nombre="Laura", apellido="Perez", usuario=None)
        out = _run(self.org.pk, self.coach_user.pk)

        assert "SKIP_NAME_AMBIGUOUS" in out

    # ── 9. User resolution: no identifier ────────────────────────────────────

    def test_skip_no_identifier(self):
        ghost = _alumno(self.coach_user, nombre="Ghost", apellido="User", usuario=None, email=None)
        out = _run(self.org.pk, self.coach_user.pk)

        assert "SKIP_NO_IDENTIFIER" in out
        # Verify no Athlete was created for this specific skipped Alumno
        # (backfill always sets notes="backfill:alumno:{pk}" on Athletes it creates)
        assert not Athlete.objects.filter(
            organization=self.org, notes=f"backfill:alumno:{ghost.pk}"
        ).exists()

    def test_email_no_match_falls_through_to_name(self):
        """email present but no User with that email → falls through to name match."""
        user_named = _user("fallthrough", first_name="Pedro", last_name="Ruiz")
        # Alumno has email that doesn't match any User, but name matches uniquely
        _alumno(
            self.coach_user,
            nombre="Pedro",
            apellido="Ruiz",
            usuario=None,
            email="nomatch@trail.org",
        )
        _run(self.org.pk, self.coach_user.pk)

        assert Athlete.objects.filter(
            user=user_named, organization=self.org
        ).exists()

    # ── 10. Membership conflict ───────────────────────────────────────────────

    def test_skip_membership_conflict_when_user_is_coach(self):
        """User already has a coach Membership in the org → no Athlete created."""
        user_coach = _user("coachconflict")
        Membership.objects.create(
            user=user_coach, organization=self.org, role=Membership.Role.COACH
        )
        _alumno(self.coach_user, usuario=user_coach)
        out = _run(self.org.pk, self.coach_user.pk)

        assert "SKIP_MEMBERSHIP_CONFLICT" in out
        assert not Athlete.objects.filter(user=user_coach, organization=self.org).exists()

    def test_existing_athlete_membership_allows_idempotent_create(self):
        """User already has an athlete Membership → Athlete is created (or already exists)."""
        Membership.objects.create(
            user=self.athlete_user,
            organization=self.org,
            role=Membership.Role.ATHLETE,
        )
        _alumno(self.coach_user, usuario=self.athlete_user)
        out = _run(self.org.pk, self.coach_user.pk)

        # Athlete created; membership already existed
        assert Athlete.objects.filter(
            user=self.athlete_user, organization=self.org
        ).exists()
        assert "SKIP_MEMBERSHIP_CONFLICT" not in out

    # ── 11. Team resolution ───────────────────────────────────────────────────

    def test_team_resolved_if_p1_team_exists(self):
        p1_team = Team.objects.create(organization=self.org, name="Elite")
        equipo = Equipo.objects.create(nombre="Elite", entrenador=self.coach_user)
        _alumno(self.coach_user, usuario=self.athlete_user, equipo=equipo)
        _run(self.org.pk, self.coach_user.pk)

        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        assert athlete.team == p1_team

    def test_team_null_if_p1_team_not_found(self):
        """Missing P1 Team must not block the backfill."""
        equipo = Equipo.objects.create(nombre="Nonexistent", entrenador=self.coach_user)
        _alumno(self.coach_user, usuario=self.athlete_user, equipo=equipo)
        out = _run(self.org.pk, self.coach_user.pk)

        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        assert athlete.team is None
        assert "CREATED" in out

    def test_team_null_when_alumno_has_no_equipo(self):
        _alumno(self.coach_user, usuario=self.athlete_user, equipo=None)
        _run(self.org.pk, self.coach_user.pk)

        athlete = Athlete.objects.get(user=self.athlete_user, organization=self.org)
        assert athlete.team is None

    # ── 12. --alumno-id filter ────────────────────────────────────────────────

    def test_single_alumno_id_processes_only_that_record(self):
        user2 = _user("athlete2")
        alumno1 = _alumno(self.coach_user, nombre="Ana", usuario=self.athlete_user)
        _alumno(self.coach_user, nombre="Bob", usuario=user2)
        _run(self.org.pk, self.coach_user.pk, alumno_id=alumno1.pk)

        assert Athlete.objects.filter(
            user=self.athlete_user, organization=self.org
        ).exists()
        assert not Athlete.objects.filter(user=user2, organization=self.org).exists()

    # ── 13. Tenancy ───────────────────────────────────────────────────────────

    def test_athlete_scoped_to_correct_org_only(self):
        org2 = _org("other-org")
        _alumno(self.coach_user, usuario=self.athlete_user)
        _run(self.org.pk, self.coach_user.pk)

        # Athlete for athlete_user must land in self.org only, never in org2
        assert Athlete.objects.filter(user=self.athlete_user, organization=self.org).count() == 1
        assert Athlete.objects.filter(user=self.athlete_user, organization=org2).count() == 0

    # ── 14. Summary output ────────────────────────────────────────────────────

    def test_summary_output_includes_totals(self):
        _alumno(self.coach_user, usuario=self.athlete_user)
        out = _run(self.org.pk, self.coach_user.pk)

        assert "Total=" in out
        assert "Created=" in out
        assert "Exists=" in out

    def test_empty_queryset_shows_warning(self):
        # No Alumno records exist for a specific non-existent id
        out = _run(self.org.pk, self.coach_user.pk, alumno_id=99999)

        assert "No Alumno records found" in out
