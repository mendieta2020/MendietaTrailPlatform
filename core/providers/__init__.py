# Provider package for OAuth integrations
from .registry import get_provider, register_provider, list_providers

__all__ = ['get_provider', 'register_provider', 'list_providers']
