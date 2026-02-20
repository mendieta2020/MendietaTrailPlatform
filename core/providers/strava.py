"""
Strava OAuth integration provider implementation.
"""
import logging
import requests
from urllib.parse import urlencode
from django.conf import settings
from typing import Dict, List
from datetime import datetime

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

    @property
    def enabled(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        """Strava supports token refresh and activity fetch."""
        return {
            "supports_refresh": True,
            "supports_activity_fetch": True,
            "supports_webhooks": True,
            "supports_workout_push": False,  # Not implemented yet
        }
    
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
    
    def refresh_token(self, refresh_token: str) -> Dict:
        """
        Refresh Strava access token using refresh token.
        
        Args:
            refresh_token: Refresh token from previous token exchange
        
        Returns:
            dict with: access_token, refresh_token, expires_at
        
        Raises:
            requests.HTTPError: If refresh fails (4xx/5xx)
        """
        token_url = "https://www.strava.com/oauth/token"
        
        data = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        
        logger.debug("strava.token_refresh", extra={
            "url": token_url,
        })
        
        try:
            response = requests.post(token_url, data=data, timeout=10)
            
            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("strava.token_refresh.rate_limited", extra={
                    "status_code": 429,
                    "retry_after": response.headers.get("Retry-After"),
                })
                response.raise_for_status()  # Will raise HTTPError with 429
            
            response.raise_for_status()
            
            token_data = response.json()
            
            logger.debug("strava.token_refresh.success", extra={
                "has_access_token": "access_token" in token_data,
                "expires_at": token_data.get("expires_at"),
            })
            
            return token_data
            
        except requests.exceptions.Timeout:
            logger.error("strava.token_refresh.timeout")
            raise
        except requests.exceptions.RequestException as e:
            logger.error("strava.token_refresh.error", extra={
                "error": str(e),
                "status_code": e.response.status_code if hasattr(e, 'response') and e.response else None,
            })
            raise
    
    def fetch_activities(self, access_token: str, after: datetime, before: datetime = None) -> List[Dict]:
        """
        Fetch activities from Strava API using GET /athlete/activities.
        
        Args:
            access_token: Valid access token
            after: Fetch activities after this timestamp
            before: Optional cutoff timestamp
        
        Returns:
            List of activity dicts (raw Strava format)
        
        Raises:
            requests.HTTPError: If API call fails (rate limit, auth, etc)
        """
        activities_url = "https://www.strava.com/api/v3/athlete/activities"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        
        # Strava expects unix timestamps
        params = {
            "after": int(after.timestamp()),
            "per_page": 200,  # Max allowed by Strava
        }
        
        if before:
            params["before"] = int(before.timestamp())
        
        logger.debug("strava.fetch_activities", extra={
            "url": activities_url,
            "after": after.isoformat(),
            "before": before.isoformat() if before else None,
        })
        
        try:
            response = requests.get(activities_url, headers=headers, params=params, timeout=30)
            
            # Handle rate limiting (Strava: 100 req/15min, 1000 req/day)
            if response.status_code == 429:
                rate_limit_usage = response.headers.get("X-RateLimit-Usage", "unknown")
                rate_limit_limit = response.headers.get("X-RateLimit-Limit", "unknown")
                logger.warning("strava.fetch_activities.rate_limited", extra={
                    "status_code": 429,
                    "rate_limit_usage": rate_limit_usage,
                    "rate_limit_limit": rate_limit_limit,
                })
                response.raise_for_status()  # Will raise HTTPError with 429
            
            # Handle auth errors
            if response.status_code == 401:
                logger.error("strava.fetch_activities.unauthorized", extra={
                    "status_code": 401,
                    "message": "Access token invalid or expired",
                })
                response.raise_for_status()
            
            response.raise_for_status()
            
            activities = response.json()
            
            logger.info("strava.fetch_activities.success", extra={
                "activity_count": len(activities),
                "after": after.isoformat(),
            })
            
            return activities
            
        except requests.exceptions.Timeout:
            logger.error("strava.fetch_activities.timeout")
            raise
        except requests.exceptions.RequestException as e:
            logger.error("strava.fetch_activities.error", extra={
                "error": str(e),
                "status_code": e.response.status_code if hasattr(e, 'response') and e.response else None,
            })
            raise

