"""
Strava integration service layer.
Provides domain-level helpers decoupled from models and views.
"""
from allauth.socialaccount.models import SocialAccount

def get_strava_connection(user):
    """
    Returns the Strava SocialAccount if it exists, else None.
    This is the ONLY authoritative source of truth for Strava connection state.
    """
    if not user or not user.is_authenticated:
        return None
    return SocialAccount.objects.filter(user=user, provider="strava").first()

def is_strava_connected(user, organization=None):
    """
    Returns True if the user has a valid Strava connection.
    This is the SINGLE AUTHORITATIVE statement of connection status.
    """
    return get_strava_connection(user) is not None
