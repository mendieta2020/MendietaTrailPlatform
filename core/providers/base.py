"""
Abstract base class for OAuth integration providers.

Each provider (Strava, Garmin, Coros, Suunto) implements this interface.

Design: Capability-based (not rigid abstract methods).
Providers declare what they support via capabilities() to avoid forcing
unsupported features on all providers.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from datetime import datetime


class IntegrationProvider(ABC):
    """
    Abstract base for OAuth integration providers.
    
    Design pattern: Strategy pattern for multi-provider support.
    Each provider implements this interface to handle OAuth flow specifics.
    
    Capability-based design: Providers declare what they support (refresh, fetch, webhooks)
    instead of forcing rigid abstract methods that may not apply to all providers.
    """
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """
        Provider identifier (e.g., 'strava', 'garmin', 'coros').
        Used in URLs, database keys, and state payloads.
        """
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable provider name (e.g., 'Strava', 'Garmin Connect').
        Used in UI and error messages.
        """
        pass
    
    @abstractmethod
    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """
        Build OAuth authorization URL with state and callback.
        
        Args:
            state: Signed state parameter with user/alumno context
            callback_uri: Full callback URI (e.g., https://example.com/api/integrations/strava/callback)
        
        Returns:
            OAuth authorization URL to redirect user to provider's auth page
        """
        pass
    
    @abstractmethod
    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth callback
            callback_uri: Same callback URI used in authorization request (required by some providers)
        
        Returns:
            dict with:
              - access_token: str (required)
              - refresh_token: str (optional, for token refresh)
              - expires_at: int (optional, unix timestamp)
              - athlete/user: dict (provider-specific user data)
        
        Raises:
            Exception: If token exchange fails (HTTP error, invalid response, etc)
        """
        pass
    
    @abstractmethod
    def get_external_user_id(self, token_data: Dict) -> str:
        """
        Extract external user ID from token response.
        
        Args:
            token_data: Response from exchange_code_for_token()
        
        Returns:
            External user ID as string (e.g., Strava athlete_id)
        
        Raises:
            ValueError: If user ID cannot be extracted
        """
        pass
    
    # --- CAPABILITY-BASED DESIGN ---
    
    def capabilities(self) -> Dict[str, bool]:
        """
        Declare provider capabilities (what features this provider supports).
        
        Returns:
            dict with boolean flags:
              - supports_refresh: Can refresh access tokens
              - supports_activity_fetch: Can fetch activities via API
              - supports_webhooks: Supports webhook subscriptions
              - supports_workout_push: Can push structured workouts to device
        
        Default: All capabilities disabled (safest for new providers).
        Override this method to enable capabilities.
        """
        return {
            "supports_refresh": False,
            "supports_activity_fetch": False,
            "supports_webhooks": False,
            "supports_workout_push": False,
        }
    
    # --- OPTIONAL CAPABILITY METHODS ---
    # Providers only implement these if they declare the capability.
    
    def refresh_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token.
        
        Only implement if capabilities()['supports_refresh'] == True.
        
        Args:
            refresh_token: Refresh token from previous token exchange
        
        Returns:
            dict with: access_token, refresh_token, expires_at
        
        Raises:
            NotImplementedError: If provider doesn't support refresh
            Exception: If refresh fails (HTTP error, etc)
        """
        raise NotImplementedError(f"{self.provider_id} does not support token refresh")
    
    def fetch_activities(self, access_token: str, after: datetime, before: datetime = None) -> List[Dict]:
        """
        Fetch activities from provider API.
        
        Only implement if capabilities()['supports_activity_fetch'] == True.
        
        Args:
            access_token: Valid access token
            after: Fetch activities after this timestamp
            before: Optional cutoff timestamp
        
        Returns:
            List of activity dicts (provider-specific format, raw JSON)
        
        Raises:
            NotImplementedError: If provider doesn't support activity fetch
            Exception: If fetch fails (HTTP error, rate limit, etc)
        """
        raise NotImplementedError(f"{self.provider_id} does not support activity fetch")

