import pytest
from core.providers import SUPPORTED_PROVIDERS
from core.provider_capabilities import (
    PROVIDER_CAPABILITIES,
    provider_supports,
    CAP_OUTBOUND_WORKOUTS,
    CAP_INBOUND_ACTIVITIES
)

class TestProviderCapabilities:
    def test_capabilities_keys_match_supported_providers(self):
        assert set(PROVIDER_CAPABILITIES.keys()) == set(SUPPORTED_PROVIDERS)

    def test_strava_does_not_support_outbound_workouts(self):
        assert provider_supports("strava", CAP_OUTBOUND_WORKOUTS) is False

    def test_unknown_provider_fail_closed(self):
        assert provider_supports("unknown_provider", CAP_INBOUND_ACTIVITIES) is False
