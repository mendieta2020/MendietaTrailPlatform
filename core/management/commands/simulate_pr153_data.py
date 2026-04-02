"""
core/management/commands/simulate_pr153_data.py

Idempotent data-simulation command for PR-153.

Creates:
  - 60 days of CYCLING activities for Atleta Test (3x/week)
  - 60 days of CYCLING activities for Carlos Test (2x/week)
  - 30 days of WellnessCheckIn for all active athletes

After creation, triggers PMC recompute for affected athletes.

Idempotency: checks for existing records before creating; safe to rerun.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

_CYCLING_SCHEDULE = {
    "atleta test": {  # days of week to train (0=Mon, 6=Sun)
        "days": {0, 2, 4},  # Mon/Wed/Fri — 3x/week
        "dist_km_range": (40, 80),
        "avg_hr": 140,
        "elev_gain_m": 400,
    },
    "carlos test": {
        "days": {1, 4},  # Tue/Thu — 2x/week
        "dist_km_range": (30, 50),
        "avg_hr": 135,
        "elev_gain_m": 300,
    },
}


class Command(BaseCommand):
    help = "PR-153: simulate cycling activities + wellness check-ins (idempotent)"

    def handle(self, *args, **options):
        from core.models import Alumno, Athlete, CompletedActivity, Organization, WellnessCheckIn
        from core.services_pmc import process_activity_load

        today = timezone.now().date()
        rng = random.Random(153)  # fixed seed for reproducibility

        # ── Cycling activities ──────────────────────────────────────────────
        created_activities = 0
        skipped_activities = 0

        for name_key, cfg in _CYCLING_SCHEDULE.items():
            # Match alumni by name (case-insensitive partial)
            first = name_key.split()[0].capitalize()
            alumnos = Alumno.objects.filter(nombre__icontains=first)
            if not alumnos.exists():
                self.stdout.write(self.style.WARNING(
                    f"  No Alumno found for '{name_key}' — skipping cycling data"
                ))
                continue

            for alumno in alumnos:
                # Resolve organization via CompletedActivity or Organization fallback
                existing_act = CompletedActivity.objects.filter(alumno=alumno).first()
                if not existing_act:
                    self.stdout.write(self.style.WARNING(
                        f"  {alumno.nombre}: no existing CompletedActivity — "
                        f"cannot resolve org. Skipping."
                    ))
                    continue
                org = existing_act.organization

                self.stdout.write(f"  Generating CYCLING for {alumno.nombre} (org {org.pk})...")

                for days_ago in range(60, 0, -1):
                    activity_date = today - timedelta(days=days_ago)
                    weekday = activity_date.weekday()
                    if weekday not in cfg["days"]:
                        continue

                    provider_id = f"pr153_cycling_{alumno.pk}_{activity_date.isoformat()}"
                    if CompletedActivity.objects.filter(
                        organization=org,
                        provider="manual",
                        provider_activity_id=provider_id,
                    ).exists():
                        skipped_activities += 1
                        continue

                    dist_km = rng.uniform(*cfg["dist_km_range"])
                    dist_m = dist_km * 1000
                    # Average cycling pace ~25 km/h
                    duration_s = int((dist_km / 25.0) * 3600)
                    hr_jitter = rng.randint(-10, 10)
                    elev_jitter = rng.randint(-50, 100)

                    act = CompletedActivity.objects.create(
                        organization=org,
                        alumno=alumno,
                        sport="CYCLING",
                        start_time=timezone.make_aware(
                            timezone.datetime.combine(
                                activity_date,
                                timezone.datetime.min.time().replace(hour=7, minute=0),
                            )
                        ),
                        duration_s=duration_s,
                        distance_m=round(dist_m, 1),
                        elevation_gain_m=round(max(0, cfg["elev_gain_m"] + elev_jitter), 1),
                        avg_hr=cfg["avg_hr"] + hr_jitter,
                        provider="manual",
                        provider_activity_id=provider_id,
                    )
                    created_activities += 1

                    # Trigger PMC recompute for activities with Athlete FK
                    if act.athlete_id:
                        try:
                            process_activity_load(act.pk)
                        except Exception as exc:
                            self.stdout.write(self.style.WARNING(f"    PMC recompute failed: {exc}"))

        self.stdout.write(
            f"  Cycling: created={created_activities}, skipped={skipped_activities}"
        )

        # ── Wellness check-ins ────────────────────────────────────────────────
        created_wellness = 0
        skipped_wellness = 0

        athletes = Athlete.objects.select_related("user", "organization").filter(
            organization__isnull=False
        )
        if not athletes.exists():
            self.stdout.write(self.style.WARNING(
                "  No Athlete records found — skipping wellness simulation"
            ))
        else:
            for athlete in athletes:
                org = athlete.organization
                for days_ago in range(30, 0, -1):
                    check_date = today - timedelta(days=days_ago)
                    if WellnessCheckIn.objects.filter(
                        athlete=athlete, date=check_date
                    ).exists():
                        skipped_wellness += 1
                        continue

                    WellnessCheckIn.objects.create(
                        athlete=athlete,
                        organization=org,
                        date=check_date,
                        sleep_quality=rng.randint(2, 5),
                        mood=rng.randint(2, 5),
                        energy=rng.randint(2, 5),
                        muscle_soreness=rng.randint(1, 5),
                        stress=rng.randint(2, 5),
                    )
                    created_wellness += 1

        self.stdout.write(
            f"  Wellness: created={created_wellness}, skipped={skipped_wellness}"
        )
        self.stdout.write(self.style.SUCCESS("PR-153 simulation complete."))
