from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Reclasifica Actividad.tipo_deporte usando strava_sport_type y dispara recompute PMC."

    def add_arguments(self, parser):
        parser.add_argument("--alumno-id", type=int, required=True)

    def handle(self, *args, **options):
        alumno_id = options.get("alumno_id")
        if not alumno_id:
            raise CommandError("--alumno-id es requerido")

        # Ejecutamos en modo sync (no depende de broker) para debugging/local.
        from core.tasks import reclassify_activities_for_alumno

        result = reclassify_activities_for_alumno(alumno_id=int(alumno_id))
        self.stdout.write(self.style.SUCCESS(str(result)))

