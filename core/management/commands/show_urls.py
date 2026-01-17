from __future__ import annotations

from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver


def _iter_patterns(urlpatterns, prefix: str = ""):
    for pattern in urlpatterns:
        if isinstance(pattern, URLPattern):
            yield f"{prefix}{pattern.pattern}"
        elif isinstance(pattern, URLResolver):
            yield from _iter_patterns(pattern.url_patterns, prefix=f"{prefix}{pattern.pattern}")


class Command(BaseCommand):
    help = "List URL patterns. Optionally filter by substring."

    def add_arguments(self, parser):
        parser.add_argument("--filter", dest="filter", help="Substring filter for URL patterns.")

    def handle(self, *args, **options):
        substring = options.get("filter")
        resolver = get_resolver()
        patterns = sorted(_iter_patterns(resolver.url_patterns))
        if substring:
            patterns = [p for p in patterns if substring in p]
        for pattern in patterns:
            self.stdout.write(pattern)
