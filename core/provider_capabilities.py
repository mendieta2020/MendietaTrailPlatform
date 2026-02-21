from core.providers import SUPPORTED_PROVIDERS

CAP_INBOUND_ACTIVITIES = "inbound_activities"
CAP_OUTBOUND_WORKOUTS = "outbound_workouts"
CAP_WEBHOOKS = "webhooks"
CAP_BACKFILL = "backfill"

PROVIDER_CAPABILITIES: dict[str, set[str]] = {
    "strava": {CAP_INBOUND_ACTIVITIES, CAP_WEBHOOKS, CAP_BACKFILL},
}

# Add default baseline capabilities for any provider in SUPPORTED_PROVIDERS 
# that is not explicitly configured above.
for _provider in SUPPORTED_PROVIDERS:
    if _provider not in PROVIDER_CAPABILITIES:
        PROVIDER_CAPABILITIES[_provider] = {CAP_INBOUND_ACTIVITIES}

def provider_supports(provider: str, capability: str) -> bool:
    """
    Check if a provider supports a specific capability.
    Fail-closed: returns False if provider is unknown or doesn't have the capability.
    Returns False instead of raising exceptions for safe use in endpoints.
    """
    if provider not in SUPPORTED_PROVIDERS:
        return False
    return capability in PROVIDER_CAPABILITIES.get(provider, set())
