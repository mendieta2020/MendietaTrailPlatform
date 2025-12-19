import json
import re
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialApp

from core.strava_oauth_views import sanitize_oauth_payload


def _strip_port(domain: str) -> str:
    if not domain:
        return domain
    # soporta "127.0.0.1:8000" -> "127.0.0.1"
    return domain.split(":", 1)[0]


def _has_port(domain: str) -> bool:
    return bool(domain and ":" in domain)


def _normalize_domain(domain: str) -> str:
    domain = (domain or "").strip()
    domain = re.sub(r"^https?://", "", domain)
    domain = domain.rstrip("/")
    return domain


class Command(BaseCommand):
    help = (
        "Diagnostica configuración Strava OAuth (django-allauth): Sites, SocialApp y token exchange.\n"
        "Uso típico (local): python3 manage.py strava_oauth_doctor --domain 127.0.0.1 --port 8000 --fix-site-domain --fix-socialapp-site"
    )

    def add_arguments(self, parser):
        parser.add_argument("--domain", default="127.0.0.1", help="Dominio esperado SIN puerto (default: 127.0.0.1)")
        parser.add_argument("--port", default="8000", help="Puerto esperado (default: 8000)")
        parser.add_argument("--scheme", default="http", help="Scheme (default: http)")

        parser.add_argument("--fix-site-domain", action="store_true", help="Si Site.domain incluye puerto, lo corrige")
        parser.add_argument(
            "--fix-socialapp-site",
            action="store_true",
            help="Asocia SocialApp(provider=strava) al Site actual (según SITE_ID)",
        )

        parser.add_argument("--exchange-code", help="Intercambia un authorization code por token (diagnóstico)")
        parser.add_argument(
            "--redirect-uri",
            help="Override del redirect_uri para el token exchange (default: construido con --scheme/--domain/--port)",
        )

    def handle(self, *args, **options):
        domain = _normalize_domain(options["domain"])
        port = str(options["port"])
        scheme = options["scheme"]

        expected_callback = f"{scheme}://{domain}:{port}/accounts/strava/login/callback/"
        self.stdout.write(self.style.MIGRATE_HEADING("Strava OAuth doctor"))
        self.stdout.write(f"- SITE_ID: {settings.SITE_ID}")
        self.stdout.write(f"- Expected callback: {expected_callback}")
        self.stdout.write("")

        # --- Sites ---
        site = Site.objects.get_current()
        self.stdout.write(self.style.MIGRATE_LABEL("Sites"))
        self.stdout.write(f"- Current Site: id={site.id} domain={site.domain!r} name={site.name!r}")
        if _has_port(site.domain):
            self.stdout.write(
                self.style.WARNING(
                    "WARN: Site.domain contiene puerto. Recomendado: domain sin puerto (e.g. '127.0.0.1')."
                )
            )
            if options["fix_site_domain"]:
                new_domain = _strip_port(site.domain)
                if not new_domain:
                    new_domain = domain
                site.domain = new_domain
                # name puede mantener el puerto si querés (solo UX)
                site.save(update_fields=["domain"])
                self.stdout.write(self.style.SUCCESS(f"OK: Site.domain actualizado a {site.domain!r}"))
        else:
            self.stdout.write(self.style.SUCCESS("OK: Site.domain sin puerto"))

        self.stdout.write("")

        # --- SocialApp ---
        self.stdout.write(self.style.MIGRATE_LABEL("SocialApp (strava)"))
        qs = SocialApp.objects.filter(provider="strava")
        if not qs.exists():
            # allauth>=65 también tiene provider_id (pero provider suele estar poblado).
            qs = SocialApp.objects.filter(provider_id="strava")

        apps = list(qs)
        if not apps:
            self.stdout.write(self.style.WARNING("WARN: No hay SocialApp configurada para provider=strava en DB."))
        else:
            for app in apps:
                sites = list(app.sites.all())
                self.stdout.write(
                    f"- SocialApp id={app.id} provider={getattr(app,'provider',None)!r} provider_id={getattr(app,'provider_id',None)!r} "
                    f"client_id={getattr(app,'client_id',None)!r} sites={[s.domain for s in sites]}"
                )
                if site not in sites:
                    self.stdout.write(self.style.WARNING("  WARN: SocialApp NO está asociada al Site actual."))
                    if options["fix_socialapp_site"]:
                        app.sites.add(site)
                        self.stdout.write(self.style.SUCCESS("  OK: SocialApp asociada al Site actual."))
                else:
                    self.stdout.write(self.style.SUCCESS("  OK: SocialApp asociada al Site actual."))

        self.stdout.write("")

        # --- Token exchange (opcional) ---
        code = options.get("exchange_code")
        if not code:
            self.stdout.write(self.style.MIGRATE_LABEL("Token exchange"))
            self.stdout.write("- Skipped (no --exchange-code)")
            return

        self.stdout.write(self.style.MIGRATE_LABEL("Token exchange"))
        redirect_uri = options.get("redirect_uri") or expected_callback
        parsed = urlparse(redirect_uri)
        if not parsed.scheme or not parsed.netloc:
            raise SystemExit(f"--redirect-uri inválida: {redirect_uri!r}")

        # Preferir settings, fallback a SocialApp.
        client_id = getattr(settings, "STRAVA_CLIENT_ID", "") or ""
        client_secret = getattr(settings, "STRAVA_CLIENT_SECRET", "") or ""
        if (not client_id or not client_secret) and apps:
            client_id = client_id or getattr(apps[0], "client_id", "") or ""
            client_secret = client_secret or getattr(apps[0], "secret", "") or ""

        if not client_id or not client_secret:
            raise SystemExit("Faltan credenciales Strava (STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET o SocialApp).")

        token_url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        # Log seguro (sin secretos)
        safe_payload = {**payload, "client_secret": "<redacted>", "code": f"<len={len(code)}>"}
        self.stdout.write(f"- POST {token_url}")
        self.stdout.write(f"- payload={safe_payload}")

        resp = requests.post(token_url, data=payload, timeout=20)
        content_type = resp.headers.get("content-type", "")
        body = None
        try:
            if content_type.split(";")[0] == "application/json":
                body = resp.json()
            else:
                body = resp.text
        except Exception:
            body = resp.text

        self.stdout.write(f"- status={resp.status_code} content_type={content_type}")
        self.stdout.write(f"- body={json.dumps(sanitize_oauth_payload(body), ensure_ascii=False)}")

        if resp.status_code not in (200, 201):
            self.stdout.write(self.style.ERROR("ERROR: token exchange falló (ver body arriba)."))
            return

        # éxito (no imprimir tokens)
        self.stdout.write(self.style.SUCCESS("OK: token exchange exitoso (tokens redacted en output)."))

