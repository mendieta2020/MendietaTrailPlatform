"""
Provider registry for OAuth integrations.

Centralized registry pattern for managing multiple OAuth providers.
Add new providers by implementing IntegrationProvider and calling register_provider().
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
        logger.warning(f"provider.registry.duplicate", extra={
            "provider_id": provider_id,
            "action": "replacing",
        })
    
    _PROVIDERS[provider_id] = provider
    
    logger.info(f"provider.registry.registered", extra={
        "provider_id": provider_id,
        "display_name": provider.display_name,
    })


def get_provider(provider_id: str) -> Optional[IntegrationProvider]:
    """
    Get provider by ID.
    
    Args:
        provider_id: Provider identifier (e.g., 'strava', 'garmin')
    
    Returns:
        IntegrationProvider instance or None if not found
    
    Example:
        provider = get_provider('strava')
        if provider:
            oauth_url = provider.get_oauth_authorize_url(state, callback_uri)
    """
    return _PROVIDERS.get(provider_id)


def list_providers() -> Dict[str, IntegrationProvider]:
    """
    List all registered providers.
    
    Returns:
        Dict mapping provider_id -> IntegrationProvider instance
    
    Example:
        for provider_id, provider in list_providers().items():
            print(f"{provider_id}: {provider.display_name}")
    """
    return dict(_PROVIDERS)


# Auto-register providers on module import
# Add new providers here as they're implemented
register_provider(StravaProvider())

# Future providers (example):
# register_provider(GarminProvider())
# register_provider(CorosProvider())
# register_provider(SuuntoProvider())

logger.info(f"provider.registry.initialized", extra={
    "provider_count": len(_PROVIDERS),
    "providers": list(_PROVIDERS.keys()),
})
