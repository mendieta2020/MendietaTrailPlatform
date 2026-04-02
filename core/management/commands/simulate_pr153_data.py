"""
core/management/commands/simulate_pr153_data.py

Idempotent data-simulation command for PR-153.

Creates (for every Alumno that already has at least one CompletedActivity):
  - 60 days of CYCLING activities  (2x/week, Tue+Thu)
  - 60 days of STRENGTH activities (2x/week, Mon+Wed)
  - 30 days of WellnessCheckIn for every Athlete in the database

Idempotency: checks for existing records before creating; safe to rerun.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

# Days of week for each sport (0=Mon, … 6=Sun)
_CYCLING_DAYS = {1, 4}   # Tue, Thu
_STRENGTH_DAYS = {0, 2}  # Mon, Wed


class Command(BaseCommand):
    help = "PR-153: simulate cycling + strength activities + wellness check-ins (idempotent)"

    def handle(self, *args, **options):
        from core.models import Alumno, Athlete, CompletedActivity, WellnessCheckIn
        from core.services_pmc import process_activity_load

        today = timezone.now().date()
        rng = random.Random(153)  # fixed seed for reproducibility

        # ── Find Alumnos that already have activity data ────────────────────
        # Limit to Alumnos that have at least one existing CompletedActivity
        # so we don't generate data for inactive / orphan records.
        active_alumno_ids = (
            CompletedActivity.objects
            .values_list("alumno_id", flat=True)
            .distinct()
        )
        alumnos = Alumno.objects.filter(pk__in=active_alumno_ids)

        if not alumnos.exists():
            self.stdout.write(self.style.WARNING(
                "No Alumno records with existing activities found — nothing to simulate."
            ))
            return

        self.stdout.write(f"Found {alumnos.count()} active Alumno(s) to simulate.")

        created_acts = 0
        skipped_acts = 0

        for alumno in alumnos:
            # Resolve org from any existing activity
            existing = CompletedActivity.objects.filter(alumno=alumno).first()
            if not existing:
                continue
            org = existing.organization

            self.stdout.write(f"  {alumno.nombre} {alumno.apellido} (alumno_id={alumno.pk}, org={org.pk})")

            # ── CYCLING (Tue + Thu) ────────────────────────────────────────
            for days_ago in range(60, 0, -1):
                act_date = today - timedelta(days=days_ago)
                if act_date.weekday() not in _CYCLING_DAYS:
                    continue

                pid = f"pr153_cycling_{alumno.pk}_{act_date.isoformat()}"
                if CompletedActivity.objects.filter(organization=org, provider="manual", provider_activity_id=pid).exists():
                    skipped_acts += 1
                    continue

                dist_km = rng.uniform(30, 60)
                act = CompletedActivity.objects.create(
                    organization=org,
                    alumno=alumno,
                    sport="CYCLING",
                    start_time=timezone.make_aware(
                        timezone.datetime.combine(act_date, timezone.datetime.min.time().replace(hour=7))
                    ),
                    duration_s=int((dist_km / 25.0) * 3600),
                    distance_m=round(dist_km * 1000, 1),
                    elevation_gain_m=round(rng.uniform(150, 500), 1),
                    avg_hr=rng.randint(130, 150),
                    provider="manual",
                    provider_activity_id=pid,
                )
                created_acts += 1
                if act.athlete_id:
                    try:
                        process_activity_load(act.pk)
                    except Exception as exc:
                        self.stdout.write(self.style.WARNING(f"    PMC recompute failed: {exc}"))

            # ── STRENGTH (Mon + Wed) ───────────────────────────────────────
            for days_ago in range(60, 0, -1):
                act_date = today - timedelta(days=days_ago)
                if act_date.weekday() not in _STRENGTH_DAYS:
                    continue

                pid = f"pr153_strength_{alumno.pk}_{act_date.isoformat()}"
                if CompletedActivity.objects.filter(organization=org, provider="manual", provider_activity_id=pid).exists():
                    skipped_acts += 1
                    continue

                dur_s = rng.randint(45, 60) * 60
                act = CompletedActivity.objects.create(
                    organization=org,
                    alumno=alumno,
                    sport="STRENGTH",
                    start_time=timezone.make_aware(
                        timezone.datetime.combine(act_date, timezone.datetime.min.time().replace(hour=18))
                    ),
                    duration_s=dur_s,
                    distance_m=0.0,
                    elevation_gain_m=None,
                    avg_hr=rng.randint(125, 140),
                    provider="manual",
                    provider_activity_id=pid,
                )
                created_acts += 1
                if act.athlete_id:
                    try:
                        process_activity_load(act.pk)
                    except Exception as exc:
                        self.stdout.write(self.style.WARNING(f"    PMC recompute failed: {exc}"))

        self.stdout.write(f"  Activities: created={created_acts}, skipped={skipped_acts}")

        # ── Wellness check-ins for all Athlete objects ─────────────────────
        created_wellness = 0
        skipped_wellness = 0

        athletes = Athlete.objects.select_related("organization").filter(organization__isnull=False)
        if not athletes.exists():
            self.stdout.write(self.style.WARNING("  No Athlete records — skipping wellness"))
        else:
            for athlete in athletes:
                for days_ago in range(30, 0, -1):
                    check_date = today - timedelta(days=days_ago)
                    if WellnessCheckIn.objects.filter(athlete=athlete, date=check_date).exists():
                        skipped_wellness += 1
                        continue
                    WellnessCheckIn.objects.create(
                        athlete=athlete,
                        organization=athlete.organization,
                        date=check_date,
                        sleep_quality=rng.randint(2, 5),
                        mood=rng.randint(2, 5),
                        energy=rng.randint(2, 5),
                        muscle_soreness=rng.randint(1, 5),
                        stress=rng.randint(2, 5),
                    )
                    created_wellness += 1

        self.stdout.write(f"  Wellness: created={created_wellness}, skipped={skipped_wellness}")
        self.stdout.write(self.style.SUCCESS("PR-153 simulation complete."))
