"""
Strava OAuth integration provider implementation.
"""
import logging
import requests
from urllib.parse import urlencode
from django.conf import settings
from typing import Dict

from .base import IntegrationProvider

logger = logging.getLogger(__name__)


class StravaProvider(IntegrationProvider):
    """
    Strava OAuth integration provider.
    
    Implements OAuth 2.0 authorization code flow for Strava API.
    Documentation: https://developers.strava.com/docs/authentication/
    """
    
    @property
    def provider_id(self) -> str:
        return "strava"
    
    @property
    def display_name(self) -> str:
        return "Strava"
    
    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """
        Build Strava OAuth authorization URL.
        
        Strava requires: client_id, redirect_uri, response_type=code, scope, state
        """
        params = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "redirect_uri": callback_uri,
            "response_type": "code",
            "scope": "read,activity:read_all,profile:read_all",
            "approval_prompt": "force",  # Always show authorization screen
            "state": state,
        }
        
        authorize_url = "https://www.strava.com/oauth/authorize"
        return f"{authorize_url}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict:
        """
        Exchange Strava authorization code for access token.
        
        Strava requires: client_id, client_secret, code, grant_type
        
        Returns:
            {
                "access_token": str,
                "refresh_token": str,
                "expires_at": int (unix timestamp),
                "athlete": {
                    "id": int,
                    "username": str,
                    ...
                }
            }
        
        Raises:
            requests.HTTPError: If exchange fails (4xx/5xx)
        """
        token_url = "https://www.strava.com/oauth/token"
        
        data = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }
        
        logger.debug(f"strava.token_exchange", extra={
            "url": token_url,
            "client_id": settings.STRAVA_CLIENT_ID,
        })
        
        response = requests.post(token_url, data=data, timeout=10)
        
        # Log status (sanitize to avoid tokens in logs)
        logger.debug(f"strava.token_exchange.response", extra={
            "status_code": response.status_code,
            "has_access_token": "access_token" in response.json() if response.ok else False,
        })
        
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx
        
        return response.json()
    
    def get_external_user_id(self, token_data: Dict) -> str:
        """
        Extract Strava athlete ID from token response.
        
        Args:
            token_data: Response from exchange_code_for_token()
        
        Returns:
            Athlete ID as string (e.g., "98765432")
        
        Raises:
            ValueError: If athlete ID missing from response
        """
        athlete = token_data.get("athlete", {})
        athlete_id = athlete.get("id")
        
        if not athlete_id:
            raise ValueError("Missing athlete ID in Strava token response")
        
        # Normalize to string
        return str(int(athlete_id))
