# ADR: Capability-Based Provider Design for Multi-Provider Integration

**Status**: Accepted  
**Date**: 2026-02-13  
**Deciders**: Staff Engineer, CTO

## Context

The platform needs to support multiple fitness provider integrations (Strava, Garmin, Coros, Suunto, Polar), each with different capabilities:

- Some providers support token refresh (OAuth 2.0 refresh_token), others don't
- Some provide APIs to fetch activities, others rely only on webhooks
- Future providers may support pushing structured workouts, others may not
- Webhook implementation varies significantly across providers

**Problem**: How do we design a provider abstraction that:
1. Doesn't force rigid abstract methods on all providers
2. Allows graceful degradation when a capability isn't supported
3. Maintains fail-closed security principles
4. Makes it easy to add new providers without modifying existing code

## Decision

We adopt a **capability-based provider design** instead of forcing all providers to implement all methods.

### Design Pattern

```python
class IntegrationProvider(ABC):
    # REQUIRED: Core OAuth methods (all providers must implement)
    @abstractmethod
    def provider_id(self) -> str: ...
    
    @abstractmethod
    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str: ...
    
    @abstractmethod
    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict: ...
    
    @abstractmethod
    def get_external_user_id(self, token_data: Dict) -> str: ...
    
    # OPTIONAL: Declare capabilities (safe default: all False)
    def capabilities(self) -> Dict[str, bool]:
        """Override to enable provider-specific features."""
        return {
            "supports_refresh": False,
            "supports_activity_fetch": False,
            "supports_webhooks": False,
            "supports_workout_push": False,
        }
    
    # OPTIONAL: Capability methods (default raises NotImplementedError)
    def refresh_token(self, refresh_token: str) -> Dict:
        raise NotImplementedError(f"{self.provider_id} does not support token refresh")
    
    def fetch_activities(self, access_token: str, after: datetime, ...) -> List[Dict]:
        raise Not ImplementedError(f"{self.provider_id} does not support activity fetch")
```

### Key Principles

1. **Explicit over implicit**: Providers declare `capabilities()` instead of relying on duck-typing
2. **Fail-safe defaults**: Base class returns `False` for all capabilities
3. **Validate before using**: Call sites check `capabilities()` before invoking optional methods
4. **Graceful degradation**: Missing capability → controlled error, not crash

### Example Usage

```python
# In background sync task
provider = get_provider('strava')
if provider.capabilities()['supports_activity_fetch']:
    activities = provider.fetch_activities(token, after=last_sync)
else:
    logger.info(f"{provider.provider_id} does not support activity fetch, skipping")
```

## Consequences

### Positive

✅ **Extensibility**: New providers don't need to implement unsupported features  
✅ **Fail-closed**: Missing capabilities are explicit, not runtime surprises  
✅ **Backward compatible**: Existing Strava integration unchanged  
✅ **Self-documenting**: `capabilities()` acts as feature discovery  
✅ **Type-safe**: IDE autocomplete works, errors caught early

### Negative

⚠️ **Caller responsibility**: Call sites must check capabilities before using optional methods  
⚠️ **Verbose**: Requires `if provider.capabilities()['X']` checks  
⚠️ **Testing overhead**: Must test capability validation in addition to method logic

### Mitigations

- **Linting**: Add static analysis rules to catch missing capability checks
- **Helper utilities**: Create `@requires_capability` decorator for tasks
- **Documentation**: Provider guide clearly explains the pattern

## Alternative Considered: Mixin Classes

```python
class RefreshTokenMixin:
    def refresh_token(self, ...) -> Dict: ...

class StravaProvider(IntegrationProvider, RefreshTokenMixin, ActivityFetchMixin):
    ...
```

**Rejected because**:
- Django ORM introspection doesn't work well with multiple inheritance
- Harder to query "what can this provider do?" dynamically
- Mixins hide capabilities from introspection/serialization

## Multi-Tenant Security Implications

**Critical**: Capability checks MUST respect multi-tenant scoping.

```python
# CORRECT: Fail-closed on missing capability
if provider.capabilities()['supports_refresh']:
    token_data = provider.refresh_token(refresh_token)
else:
    # Mark integration as failed, don't attempt refresh
    status.connected = False
    status.error_reason = "provider_unsupported_refresh"
    status.save()

# WRONG: Attempt without checking capability
try:
    token_data = provider.refresh_token(refresh_token)  # May leak error info
except NotImplementedError:
    pass  # Silent failure is dangerous
```

**Rule**: Any capability-dependent code must explicitly check `capabilities()` first and fail-closed on False.

## Provider Addition Workflow

Adding a new provider now follows this pattern:

1. **Implement required methods** (provider_id, OAuth flow)
2. **Declare capabilities** via `capabilities()` method
3. **Implement only supported capability methods**
4. ** Register in registry**: `register_provider(NewProvider())`
5. **No callback changes needed**: Generic handler works automatically

## References

- Implementation: `core/providers/base.py`
- Example: `core/providers/strava.py`
- Generic callback: `core/integration_callback_views.py::_handle_generic_callback`
- Tests: `core/tests_provider_integration.py`

## Notes

This ADR represents a **P0 foundation**. Future work (P1+):
- Helper decorators: `@requires_capability('supports_refresh')`
- Capability validation in Celery tasks
- Admin UI to show provider capabilities
- Monitoring/alerting when capability assumptions fail
