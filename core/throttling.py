from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class _PathPrefixRateThrottle(SimpleRateThrottle):
    scope = ""
    path_prefixes: tuple[str, ...] = ()

    def get_rate(self):
        if not self.scope:
            return None
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        if not self.path_prefixes:
            return None
        request_path = getattr(request, "path", "") or ""
        if not any(request_path.startswith(prefix) for prefix in self.path_prefixes):
            return None

        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = self.get_ident(request)

        return self.cache_format % {"scope": self.scope, "ident": ident}


class TokenEndpointRateThrottle(_PathPrefixRateThrottle):
    scope = "token"
    path_prefixes = ("/api/token/",)


class StravaWebhookRateThrottle(_PathPrefixRateThrottle):
    scope = "strava_webhook"
    path_prefixes = ("/webhooks/strava/",)


class CoachEndpointRateThrottle(_PathPrefixRateThrottle):
    scope = "coach"
    path_prefixes = ("/api/coach/",)


class AnalyticsEndpointRateThrottle(_PathPrefixRateThrottle):
    scope = "analytics"
    path_prefixes = ("/api/analytics/",)
