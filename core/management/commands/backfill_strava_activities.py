import datetime
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Alumno, StravaWebhookEvent
from core.services import obtener_cliente_strava_para_alumno
from core.tasks import process_strava_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill: reimportar últimas N actividades Strava por Alumno (>= 30 días recomendado)."

    def add_arguments(self, parser):
        parser.add_argument("--alumno-id", type=int, help="ID del Alumno a backfillear")
        parser.add_argument("--all", action="store_true", help="Backfill para todos los alumnos con strava_athlete_id")
        parser.add_argument("--days", type=int, default=30, help="Días hacia atrás (default: 30)")
        parser.add_argument("--limit", type=int, default=200, help="Límite de actividades a encolar por alumno (default: 200)")
        parser.add_argument("--dry-run", action="store_true", help="No crea eventos ni encola tasks; solo muestra conteo")

    def handle(self, *args, **options):
        alumno_id = options.get("alumno_id")
        do_all = bool(options.get("all"))
        days = int(options.get("days") or 30)
        limit = int(options.get("limit") or 200)
        dry_run = bool(options.get("dry_run"))

        if not alumno_id and not do_all:
            raise SystemExit("Debe especificar --alumno-id o --all")

        if days < 30:
            self.stdout.write(self.style.WARNING("Aviso: se recomienda >= 30 días para backfill."))

        after = timezone.now() - datetime.timedelta(days=days)

        qs = Alumno.objects.all()
        if alumno_id:
            qs = qs.filter(id=alumno_id)
        if do_all:
            qs = qs.filter(strava_athlete_id__isnull=False).exclude(strava_athlete_id="")

        alumnos = list(qs.select_related("usuario", "entrenador"))
        if not alumnos:
            self.stdout.write(self.style.WARNING("No hay alumnos para procesar."))
            return

        total_enqueued = 0
        for alumno in alumnos:
            if not alumno.strava_athlete_id:
                self.stdout.write(self.style.WARNING(f"SKIP alumno={alumno.id}: sin strava_athlete_id"))
                continue

            client = obtener_cliente_strava_para_alumno(alumno)
            if not client:
                self.stdout.write(self.style.WARNING(f"SKIP alumno={alumno.id}: missing_strava_auth"))
                continue

            # Strava: activities del usuario autenticado por token.
            # Si el token no corresponde al atleta, esto no traerá datos del alumno (se verá en conteo=0).
            activities = list(client.get_activities(after=after, limit=limit))
            self.stdout.write(f"alumno={alumno.id} athlete_id={alumno.strava_athlete_id} fetched={len(activities)}")

            if dry_run:
                continue

            for a in activities:
                # event_uid estable para idempotencia del backfill
                start_dt = getattr(a, "start_date", None) or getattr(a, "start_date_local", None)
                start_ts = int(start_dt.timestamp()) if start_dt else int(timezone.now().timestamp())
                event_uid = f"backfill:{alumno.id}:{int(getattr(a, 'id'))}:{start_ts}"

                ev, created = StravaWebhookEvent.objects.get_or_create(
                    provider="strava",
                    event_uid=event_uid,
                    defaults={
                        "object_type": "activity",
                        "object_id": int(getattr(a, "id")),
                        "aspect_type": "create",
                        "owner_id": int(alumno.strava_athlete_id),
                        "event_time": int(timezone.now().timestamp()),
                        "payload_raw": {"backfill": True, "alumno_id": alumno.id, "days": days},
                        "status": StravaWebhookEvent.Status.QUEUED,
                    },
                )
                if created:
                    process_strava_event.delay(ev.pk)
                    total_enqueued += 1

        self.stdout.write(self.style.SUCCESS(f"OK enqueued={total_enqueued} dry_run={dry_run}"))

