"""
OAuth state management with nonce-based replay protection.
"""
import json
import logging
import uuid
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.core.signing import Signer, BadSignature

logger = logging.getLogger(__name__)

# Cache TTL for nonce (10 minutes default)
NONCE_TTL_SECONDS = int(getattr(settings, "OAUTH_NONCE_TTL_SECONDS", 600))

# Fail-open mode: allow OAuth if cache unavailable (default: False for security)
NONCE_FAIL_OPEN = getattr(settings, "OAUTH_NONCE_FAIL_OPEN", False)


def generate_oauth_state(provider: str, user_id: int, redirect_uri: str = "") -> str:
    """
    Generate OAuth state with embedded nonce for replay protection.
    
    Args:
        provider: Provider ID (e.g., "strava")
        user_id: Authenticated user's ID
        redirect_uri: Optional redirect URI for validation
    
    Returns:
        Signed state string to pass to OAuth provider
    """
    nonce = str(uuid.uuid4())
    timestamp = int(datetime.now(dt_timezone.utc).timestamp())
    
    payload = {
        "provider": provider,
        "user_id": user_id,
        "nonce": nonce,
        "ts": timestamp,
        "redirect_uri": redirect_uri,
    }
    
    # Store nonce in cache for validation
    cache_key = f"oauth_nonce:{provider}:{nonce}"
    try:
        cache.set(cache_key, {"user_id": user_id, "ts": timestamp}, timeout=NONCE_TTL_SECONDS)
    except Exception as e:
        logger.error(
            "oauth.nonce.cache_set_failed",
            extra={
                "provider": provider,
                "user_id": user_id,
                "error": str(e),
            },
        )
        if not NONCE_FAIL_OPEN:
            raise RuntimeError("Failed to store OAuth nonce in cache (fail-closed mode)") from e
    
    # Sign the payload
    signer = Signer()
    state = signer.sign(json.dumps(payload))
    
    return state


def validate_and_consume_nonce(state: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Validate OAuth state and consume nonce (one-time use).
    
    Args:
        state: Signed state string from OAuth callback
    
    Returns:
        Tuple of (payload_dict, error_reason):
        - payload_dict: Decoded state payload if valid, None otherwise
        - error_reason: Error code string if invalid, None otherwise
          Possible reasons:
          - "state_malformed": Could not decode/verify signature
          - "state_expired": Timestamp exceeds TTL
          - "nonce_invalid_or_reused": Nonce missing from cache or already consumed
          - "nonce_cache_unavailable": Cache error in fail-open mode (payload still returned)
    """
    # Decode and verify signature
    signer = Signer()
    try:
        unsigned = signer.unsign(state)
        payload = json.loads(unsigned)
    except (BadSignature, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "oauth.state.malformed",
            extra={"error": str(e), "state_prefix": state[:20] if state else ""},
        )
        return None, "state_malformed"
    
    # Extract fields
    provider = payload.get("provider", "")
    nonce = payload.get("nonce", "")
    timestamp = payload.get("ts", 0)
    user_id = payload.get("user_id")
    
    # Validate timestamp (basic replay protection even if cache fails)
    now_ts = int(datetime.now(dt_timezone.utc).timestamp())
    if now_ts - timestamp > NONCE_TTL_SECONDS:
        logger.warning(
            "oauth.state.expired",
            extra={
                "provider": provider,
                "user_id": user_id,
                "age_seconds": now_ts - timestamp,
            },
        )
        return None, "state_expired"
    
    # Validate and consume nonce from cache
    cache_key = f"oauth_nonce:{provider}:{nonce}"
    try:
        cached_value = cache.get(cache_key)
        
        if cached_value is None:
            # Nonce not in cache: either already consumed or never existed
            logger.warning(
                "oauth.nonce.not_found",
                extra={
                    "provider": provider,
                    "user_id": user_id,
                    "nonce_hash": hash(nonce) % 1000000,  # Log hash, not nonce
                },
            )
            return None, "nonce_invalid_or_reused"
        
        # Consume nonce (delete from cache)
        cache.delete(cache_key)
        
        logger.info(
            "oauth.nonce.consumed",
            extra={
                "provider": provider,
                "user_id": user_id,
                "nonce_hash": hash(nonce) % 1000000,
            },
        )
        
        return payload, None
        
    except Exception as e:
        logger.error(
            "oauth.nonce.cache_error",
            extra={
                "provider": provider,
                "user_id": user_id,
                "error": str(e),
            },
        )
        
        if NONCE_FAIL_OPEN:
            # Fail-open mode: allow but log warning
            logger.warning(
                "oauth.nonce.cache_unavailable_fail_open",
                extra={"provider": provider, "user_id": user_id},
            )
            return payload, "nonce_cache_unavailable"
        else:
            # Fail-closed mode: reject
            return None, "nonce_invalid_or_reused"
