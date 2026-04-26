import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Alumno, Athlete, Membership, Organization

logger = logging.getLogger(__name__)

User = get_user_model()

_USERS = [
    {
        "username": "owner@test.com",
        "email": "owner@test.com",
        "password": "test1234",
        "is_superuser": True,
        "is_staff": True,
        "role": Membership.Role.OWNER,
    },
    {
        "username": "coach@test.com",
        "email": "coach@test.com",
        "password": "test1234",
        "is_superuser": False,
        "is_staff": False,
        "role": Membership.Role.COACH,
    },
    {
        "username": "atleta1@test.com",
        "email": "atleta1@test.com",
        "password": "test1234",
        "is_superuser": False,
        "is_staff": False,
        "role": Membership.Role.ATHLETE,
    },
    {
        "username": "atleta2@test.com",
        "email": "atleta2@test.com",
        "password": "test1234",
        "is_superuser": False,
        "is_staff": False,
        "role": Membership.Role.ATHLETE,
    },
]

_ALUMNOS = [
    {"username": "atleta1@test.com", "nombre": "Atleta1", "apellido": "Test", "ciudad": "Buenos Aires"},
    {"username": "atleta2@test.com", "nombre": "Atleta2", "apellido": "Test", "ciudad": "Buenos Aires"},
]

# Buenos Aires coordinates for local weather testing (bypasses geocoding API)
_TEST_LAT = -34.6037
_TEST_LON = -58.3816


class Command(BaseCommand):
    help = "Seed test users for local development. Idempotent. Refuses to run when DEBUG=False."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_test_users must not run in production (DEBUG=False). "
                "Set DEBUG=True in your local .env before running this command."
            )

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            org, _ = Organization.objects.get_or_create(
                slug="test-org",
                defaults={"name": "Test Org", "is_active": True},
            )

            user_map: dict[str, User] = {}

            for spec in _USERS:
                user, user_created = User.objects.get_or_create(
                    username=spec["username"],
                    defaults={
                        "email": spec["email"],
                        "is_superuser": spec["is_superuser"],
                        "is_staff": spec["is_staff"],
                    },
                )
                if user_created:
                    user.set_password(spec["password"])
                    user.save(update_fields=["password"])
                    created_count += 1
                else:
                    updated_count += 1

                user_map[spec["username"]] = user

                Membership.objects.update_or_create(
                    user=user,
                    organization=org,
                    defaults={"role": spec["role"], "is_active": True},
                )

            coach_user = user_map["coach@test.com"]
            for alumno_spec in _ALUMNOS:
                athlete_user = user_map[alumno_spec["username"]]
                Alumno.objects.update_or_create(
                    usuario=athlete_user,
                    defaults={
                        "entrenador": coach_user,
                        "nombre": alumno_spec["nombre"],
                        "apellido": alumno_spec["apellido"],
                        "email": athlete_user.email,
                        "ciudad": alumno_spec["ciudad"],
                    },
                )
                # Seed org-first Athlete record with coordinates so local weather works
                # without a geocoding API call (Fix 9 / Fix 4).
                Athlete.objects.update_or_create(
                    user=athlete_user,
                    organization=org,
                    defaults={
                        "is_active": True,
                        "location_city": alumno_spec["ciudad"],
                        "location_lat": _TEST_LAT,
                        "location_lon": _TEST_LON,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded 4 users into Test Org (created: {created_count}, updated: {updated_count})"
            )
        )
        logger.info(
            "seed_test_users.completed",
            extra={
                "event_name": "seed_test_users.completed",
                "outcome": "success",
                "created": created_count,
                "updated": updated_count,
            },
        )
