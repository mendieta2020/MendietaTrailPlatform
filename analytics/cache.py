from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from analytics.models import AnalyticsRangeCache


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "ANALYTICS_RANGE_CACHE_TTL_SECONDS", 21600))


def is_cache_fresh(cache: AnalyticsRangeCache) -> bool:
    ttl_seconds = _cache_ttl_seconds()
    if ttl_seconds <= 0:
        return False
    return timezone.now() - cache.last_computed_at <= timedelta(seconds=ttl_seconds)


def get_range_cache(
    *,
    cache_type: str,
    alumno_id: int,
    sport: str,
    start_date,
    end_date,
) -> Any | None:
    cache = (
        AnalyticsRangeCache.objects.filter(
            cache_type=cache_type,
            alumno_id=int(alumno_id),
            sport=str(sport),
            start_date=start_date,
            end_date=end_date,
        )
        .only("payload", "last_computed_at")
        .first()
    )
    if not cache:
        return None
    if not is_cache_fresh(cache):
        return None
    return cache.payload


def set_range_cache(
    *,
    cache_type: str,
    alumno_id: int,
    sport: str,
    start_date,
    end_date,
    payload: Any,
) -> None:
    AnalyticsRangeCache.objects.update_or_create(
        cache_type=cache_type,
        alumno_id=int(alumno_id),
        sport=str(sport),
        start_date=start_date,
        end_date=end_date,
        defaults={
            "payload": payload,
            "last_computed_at": timezone.now(),
        },
    )
