from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = (
        "Audita la tabla django_migrations vs archivos de migración en disco. "
        "Opcionalmente borra registros 'stale' (aplicados pero sin archivo)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Alias de DB (default: default).",
        )
        parser.add_argument(
            "--apps",
            nargs="*",
            default=[],
            help="Opcional: lista de apps a auditar (ej: core analytics). Si se omite, audita todas.",
        )
        parser.add_argument(
            "--delete-stale",
            action="store_true",
            help="Borra registros en django_migrations que no existen en disco (PELIGROSO si se usa mal).",
        )

    def handle(self, *args, **options):
        db = options["database"]
        apps: list[str] = [a.strip() for a in (options["apps"] or []) if a and a.strip()]
        delete_stale: bool = bool(options["delete_stale"])

        connection = connections[db]
        loader = MigrationLoader(connection, ignore_no_migrations=True)

        applied = set(loader.applied_migrations)  # set[(app_label, migration_name)]
        disk = set(loader.disk_migrations.keys())

        stale = applied - disk
        if apps:
            stale = {m for m in stale if m[0] in set(apps)}

        if not stale:
            self.stdout.write(self.style.SUCCESS("OK: No hay registros stale en django_migrations."))
            return

        self.stdout.write(self.style.WARNING("Se detectaron migraciones aplicadas SIN archivo en disco:"))
        for app_label, name in sorted(stale):
            self.stdout.write(f"- {app_label}.{name}")

        if not delete_stale:
            self.stdout.write(
                self.style.NOTICE(
                    "Para borrarlas: python3 manage.py audit_django_migrations --delete-stale "
                    + ("--apps " + " ".join(apps) if apps else "")
                )
            )
            return

        # Delete stale rows with raw SQL (evita depender del modelo MigrationRecorder)
        with connection.cursor() as cursor:
            for app_label, name in sorted(stale):
                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                    [app_label, name],
                )

        self.stdout.write(self.style.SUCCESS(f"OK: Se borraron {len(stale)} registros stale."))

