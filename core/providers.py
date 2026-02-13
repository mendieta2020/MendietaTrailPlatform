"""
Multi-provider OAuth integration registry.

Defines available OAuth providers (Strava, Garmin, Coros, Suunto) and provides
a registry pattern for managing provider-specific OAuth flows.
"""
from abc import ABC, abstractmethod
from typing import Any
from django.conf import settings


class IntegrationProvider(ABC):
    """Base class for OAuth integration providers."""
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'strava')."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name (e.g., 'Strava')."""
        pass
    
    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is currently enabled for connections."""
        pass
    
    @property
    def icon_url(self) -> str:
        """Optional icon URL for frontend display."""
        return ""


class StravaProvider(IntegrationProvider):
    """Strava OAuth integration (active)."""
    
    provider_id = "strava"
    display_name = "Strava"
    enabled = True
    icon_url = "/static/icons/strava.svg"  # Optional


class GarminProvider(IntegrationProvider):
    """Garmin Connect OAuth integration (coming soon)."""
    
    provider_id = "garmin"
    display_name = "Garmin Connect"
    enabled = False  # Coming soon stub


class CorosProvider(IntegrationProvider):
    """Coros OAuth integration (coming soon)."""
    
    provider_id = "coros"
    display_name = "Coros"
    enabled = False  # Coming soon stub


class SuuntoProvider(IntegrationProvider):
    """Suunto OAuth integration (coming soon)."""
    
    provider_id = "suunto"
    display_name = "Suunto"
    enabled = False  # Coming soon stub


# Provider registry
PROVIDERS: dict[str, IntegrationProvider] = {
    "strava": StravaProvider(),
    "garmin": GarminProvider(),
    "coros": CorosProvider(),
    "suunto": SuuntoProvider(),
}


def get_provider(provider_id: str) -> IntegrationProvider | None:
    """
    Get provider instance by ID.
    
    Args:
        provider_id: Provider identifier (e.g., "strava")
    
    Returns:
        IntegrationProvider instance or None if not found
    """
    return PROVIDERS.get(provider_id)


def get_available_providers() -> list[dict[str, Any]]:
    """
    Get list of available providers for frontend catalog.
    
    Returns:
        List of dicts with provider metadata:
        [{"id": "strava", "name": "Strava", "enabled": True}, ...]
    """
    return [
        {
            "id": p.provider_id,
            "name": p.display_name,
            "enabled": p.enabled,
            "icon_url": p.icon_url if hasattr(p, 'icon_url') else "",
        }
        for p in PROVIDERS.values()
    ]


def get_enabled_providers() -> list[IntegrationProvider]:
    """Get list of enabled providers."""
    return [p for p in PROVIDERS.values() if p.enabled]
