from __future__ import annotations

from datetime import date as date_type

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from analytics.tasks import (
    recompute_injury_risk_daily,
    recompute_injury_risk_for_athlete,
    recompute_injury_risk_for_coach,
)


class Command(BaseCommand):
    help = "Encola recálculo de Injury Risk (snapshots) para una fecha."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="date", default=None, help="Fecha YYYY-MM-DD (default: hoy)")
        parser.add_argument("--coach-id", dest="coach_id", type=int, default=None, help="ID de entrenador (tenant)")
        parser.add_argument("--athlete-id", dest="athlete_id", type=int, default=None, help="ID de alumno")
        parser.add_argument(
            "--sync",
            dest="sync",
            action="store_true",
            help="Ejecuta en el proceso actual (sin Celery). Recomendado solo en local.",
        )

    def handle(self, *args, **options):
        date_iso = options["date"]
        coach_id = options["coach_id"]
        athlete_id = options["athlete_id"]
        sync = bool(options["sync"])

        if coach_id and athlete_id:
            raise CommandError("Usá solo uno: --coach-id o --athlete-id")

        # Validar fecha (si viene)
        if date_iso:
            try:
                date_type.fromisoformat(date_iso)
            except ValueError as e:
                raise CommandError("Formato inválido para --date. Use YYYY-MM-DD") from e

        if athlete_id:
            if sync:
                out = recompute_injury_risk_for_athlete(alumno_id=athlete_id, fecha_iso=date_iso)
                self.stdout.write(self.style.SUCCESS(f"OK (sync): {out}"))
                return
            recompute_injury_risk_for_athlete.delay(athlete_id, date_iso)
            self.stdout.write(self.style.SUCCESS(f"Encolado atleta={athlete_id} date={date_iso or timezone.localdate()}"))
            return

        if coach_id:
            if sync:
                out = recompute_injury_risk_for_coach(entrenador_id=coach_id, fecha_iso=date_iso)
                self.stdout.write(self.style.SUCCESS(f"OK (sync): {out}"))
                return
            recompute_injury_risk_for_coach.delay(coach_id, date_iso)
            self.stdout.write(self.style.SUCCESS(f"Encolado coach={coach_id} date={date_iso or timezone.localdate()}"))
            return

        # Default: todos los coaches
        if sync:
            out = recompute_injury_risk_daily(fecha_iso=date_iso)
            self.stdout.write(self.style.SUCCESS(f"OK (sync): {out}"))
            return

        recompute_injury_risk_daily.delay(date_iso)
        self.stdout.write(self.style.SUCCESS(f"Encolado daily date={date_iso or timezone.localdate()}"))

