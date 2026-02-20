"""
Provider registry for OAuth integrations.

Single source of truth for all registered providers.
Add new providers by implementing IntegrationProvider and calling register_provider().

Active providers (enabled=True): strava
Coming Soon stubs (enabled=False): garmin, coros, suunto, polar, wahoo
"""
from typing import Dict, Optional
import logging

from .base import IntegrationProvider
from .strava import StravaProvider

logger = logging.getLogger(__name__)

# Global provider registry (singleton pattern)
_PROVIDERS: Dict[str, IntegrationProvider] = {}


def register_provider(provider: IntegrationProvider):
    """
    Register a provider in the global registry.

    Args:
        provider: IntegrationProvider instance

    Example:
        register_provider(StravaProvider())
        register_provider(GarminProvider())
    """
    provider_id = provider.provider_id

    if provider_id in _PROVIDERS:
        logger.warning("provider.registry.duplicate", extra={
            "provider_id": provider_id,
            "action": "replacing",
        })

    _PROVIDERS[provider_id] = provider

    logger.info("provider.registry.registered", extra={
        "provider_id": provider_id,
        "display_name": provider.display_name,
        "enabled": getattr(provider, "enabled", False),
    })


def get_provider(provider_id: str) -> Optional[IntegrationProvider]:
    """
    Get provider by ID.

    Returns IntegrationProvider instance or None if not found (fail-closed).

    Example:
        provider = get_provider('strava')
        if provider:
            oauth_url = provider.get_oauth_authorize_url(state, callback_uri)
    """
    return _PROVIDERS.get(provider_id)


def list_providers() -> Dict[str, IntegrationProvider]:
    """
    List all registered providers (enabled and disabled).

    Returns:
        Dict mapping provider_id -> IntegrationProvider instance
    """
    return dict(_PROVIDERS)


def is_enabled(provider_id: str) -> bool:
    """
    Return True if provider is registered AND has enabled=True.

    Fail-closed: unknown providers return False.
    Used by IntegrationStartView to gate the 422 guard for disabled providers.

    Args:
        provider_id: e.g. 'strava', 'garmin'

    Returns:
        True only if provider is both registered and explicitly enabled.
    """
    provider = _PROVIDERS.get(provider_id)
    if not provider:
        return False
    return bool(getattr(provider, "enabled", False))


# ---------------------------------------------------------------------------
# Auto-register all providers on module import.
#
# Active (enabled=True):
#   - Strava: full OAuth, webhooks, activity sync
#
# Coming Soon (enabled=False) — registered for UI catalog only:
#   - Garmin: OAuth 1.0a (requires separate credentials)
#   - Coros:  OAuth 2.0
#   - Suunto: OAuth 2.0
#   - Polar:  OAuth 2.0 (Accesslink API)
#   - Wahoo:  OAuth 2.0 (Wahoo Cloud API)
# ---------------------------------------------------------------------------
from .garmin import GarminProvider   # noqa: E402
from .coros import CorosProvider     # noqa: E402
from .suunto import SuuntoProvider   # noqa: E402
from .polar import PolarProvider     # noqa: E402
from .wahoo import WahooProvider     # noqa: E402

register_provider(StravaProvider())
register_provider(GarminProvider())
register_provider(CorosProvider())
register_provider(SuuntoProvider())
register_provider(PolarProvider())
register_provider(WahooProvider())

logger.info("provider.registry.initialized", extra={
    "provider_count": len(_PROVIDERS),
    "providers": list(_PROVIDERS.keys()),
    "enabled": [pid for pid, p in _PROVIDERS.items() if getattr(p, "enabled", False)],
})
