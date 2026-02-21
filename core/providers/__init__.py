# Provider package for OAuth integrations
from .registry import get_provider, register_provider, list_providers

SUPPORTED_PROVIDERS = [
    "strava",
    "garmin",
    "coros",
    "suunto",
    "polar",
]

__all__ = ['get_provider', 'register_provider', 'list_providers', 'SUPPORTED_PROVIDERS']
