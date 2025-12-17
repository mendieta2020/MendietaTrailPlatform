from datetime import date as date_type

from django.core.management.base import BaseCommand, CommandError

from analytics.tasks import recompute_injury_risk_for_coach


class Command(BaseCommand):
    help = "Recalcula injury risk para un coach (tenant-scoped)."

    def add_arguments(self, parser):
        parser.add_argument("--coach-id", type=int, required=True, help="ID del coach (tenant)")
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Fecha ISO YYYY-MM-DD (opcional; default: hoy)",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Ejecuta sin celery (call directo). Default: encola con .delay()",
        )

    def handle(self, *args, **options):
        coach_id: int = options["coach_id"]
        date_str: str | None = options["date"]
        sync: bool = bool(options["sync"])

        if date_str:
            try:
                # Validación básica formato ISO
                date_type.fromisoformat(date_str)
            except ValueError as e:
                raise CommandError("--date debe ser YYYY-MM-DD") from e

        if sync:
            result = recompute_injury_risk_for_coach(coach_id, date_str)
            self.stdout.write(self.style.SUCCESS(str(result)))
        else:
            async_result = recompute_injury_risk_for_coach.delay(coach_id, date_str)
            self.stdout.write(self.style.SUCCESS(f"ENQUEUED {async_result.id}"))

