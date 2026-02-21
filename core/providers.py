"""
core/providers.py — Legacy shim (PR8 cleanup).

IMPORTANT: This file previously contained standalone provider stubs
(StravaProvider, GarminProvider, etc.). Those stubs have been moved to
the canonical registry under core/providers/ package.

This module now re-exports from the canonical registry for backward
compatibility with any code that imports directly from core.providers.

Source of truth: core/providers/registry.py
"""

# Re-export canonical functions from the registry package
from core.providers.registry import (  # noqa: F401
    get_provider,
    register_provider,
    list_providers,
    is_enabled,
)

# Re-export provider classes for any code that imports them directly
from core.providers.strava import StravaProvider    # noqa: F401
from core.providers.garmin import GarminProvider   # noqa: F401
from core.providers.coros import CorosProvider     # noqa: F401
from core.providers.suunto import SuuntoProvider   # noqa: F401
from core.providers.polar import PolarProvider     # noqa: F401
from core.providers.wahoo import WahooProvider     # noqa: F401

# ---------------------------------------------------------------------------
# PR12: SUPPORTED_PROVIDERS — Single Source of Truth
# ---------------------------------------------------------------------------
# This is the ONE authoritative list of OAuth provider slugs for MTP.
# Rules:
#   - Any new provider must be added HERE first (lowercase slug).
#   - No other module may maintain its own provider list.
#   - Consumers: import SUPPORTED_PROVIDERS from core.providers
#   - "strava" is included so that ?provider=strava returns a controlled 400
#     (Strava status lives in OAuthIntegrationStatus, not OAuthCredential).
#     The 400 message will guide callers to the correct endpoint.
# ---------------------------------------------------------------------------
SUPPORTED_PROVIDERS: list[str] = [
    "strava",
    "garmin",
    "coros",
    "suunto",
    "polar",
]

# Legacy: PROVIDERS dict kept for any consumer that imported it directly
# Points to the registry dict (same instances)
PROVIDERS = list_providers()


def get_available_providers():
    """
    DEPRECATED: Use core.providers.list_providers() directly.

    Kept for backward compatibility. Returns all registered providers
    (enabled and disabled) as a list of dicts.
    """
    providers = list_providers()
    return [
        {
            "id": p.provider_id,
            "name": p.display_name,
            "enabled": getattr(p, "enabled", False),
            "icon_url": getattr(p, "icon_url", ""),
        }
        for p in providers.values()
    ]


def get_enabled_providers():
    """
    DEPRECATED: Use core.providers.list_providers() + filter.

    Returns only enabled providers.
    """
    return [p for p in list_providers().values() if getattr(p, "enabled", False)]
