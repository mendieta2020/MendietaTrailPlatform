from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from analytics.pmc_engine import build_daily_aggs_for_alumno, recompute_pmc_for_alumno
from core.models import Alumno


class Command(BaseCommand):
    help = "Recalcula DailyActivityAgg + PMC desde core.Actividad para un atleta (scoped por coach)."

    def add_arguments(self, parser):
        parser.add_argument("--alumno-id", type=int, required=True, help="ID del alumno")
        parser.add_argument("--entrenador-id", type=int, required=True, help="ID del coach/entrenador (tenant)")
        parser.add_argument(
            "--start-date",
            type=str,
            required=True,
            help="Fecha ISO (YYYY-MM-DD) desde la cual recomputar analytics.",
        )

    def handle(self, *args, **options):
        alumno_id = int(options["alumno_id"])
        entrenador_id = int(options["entrenador_id"])
        start_date = date.fromisoformat(str(options["start_date"]))

        alumno = Alumno.objects.select_related("entrenador").filter(pk=alumno_id).first()
        if not alumno:
            raise CommandError(f"Alumno {alumno_id} no existe.")
        if alumno.entrenador_id != entrenador_id:
            raise CommandError(
                f"Scope inválido: alumno {alumno_id} pertenece a entrenador {alumno.entrenador_id}, no {entrenador_id}."
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Recomputando analytics para alumno={alumno_id} desde {start_date.isoformat()} (coach={entrenador_id})..."
            )
        )

        aggs_count = build_daily_aggs_for_alumno(alumno_id=alumno_id, start_date=start_date)
        pmc_stats = recompute_pmc_for_alumno(alumno_id=alumno_id, start_date=start_date)

        self.stdout.write(
            self.style.SUCCESS(
                f"DailyActivityAgg reconstruidos: {aggs_count}. PMC: {pmc_stats}. Fecha fin: {timezone.localdate()}."
            )
        )
