"""
Abstract base class for OAuth integration providers.

Each provider (Strava, Garmin, Coros, Suunto) implements this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional


class IntegrationProvider(ABC):
    """
    Abstract base for OAuth integration providers.
    
    Design pattern: Strategy pattern for multi-provider support.
    Each provider implements this interface to handle OAuth flow specifics.
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
