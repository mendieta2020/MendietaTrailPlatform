"""
OAuth Integration Status tracking per athlete and provider.
"""
from django.db import models
from django.utils import timezone


class OAuthIntegrationStatus(models.Model):
    """
    Per-provider OAuth connection status for each Alumno (athlete).
    
    Tracks whether an athlete has connected their account from a given provider
    (Strava, Garmin, Coros, Suunto), along with sync status and error tracking.
    
    This is the single source of truth for OAuth integration status (P0 hardening).
    """
    
    class Provider(models.TextChoices):
        STRAVA = "strava", "Strava"
        GARMIN = "garmin", "Garmin"
        COROS = "coros", "Coros"
        SUUNTO = "suunto", "Suunto"
    
    alumno = models.ForeignKey(
        "Alumno",
        on_delete=models.CASCADE,
        related_name="oauth_integrations",
        db_index=True,
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        db_index=True,
    )
    
    # Connection state
    connected = models.BooleanField(default=False, db_index=True)
    athlete_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Provider's athlete/user ID (e.g., Strava athlete_id)",
    )
    
    # Token expiry tracking (from OAuth token response)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the access token expires",
    )
    
    # Sync tracking
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful activity sync from this provider",
    )
    
    # Error tracking
    error_reason = models.CharField(
        max_length=60,
        blank=True,
        default="",
        db_index=True,
        help_text="Machine-readable error code (e.g., missing_athlete_id, invalid_code)",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Human-readable error details (not exposed to frontend)",
    )
    last_error_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    
    class Meta:
        app_label = "core"  # Explicitly set app to avoid conflicts
        verbose_name = "OAuth Integration Status"
        verbose_name_plural = "OAuth Integration Statuses"
        constraints = [
            models.UniqueConstraint(
                fields=["alumno", "provider"],
                name="uniq_oauth_integration_per_athlete_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "connected"]),
            models.Index(fields=["alumno", "-updated_at"]),
        ]
    
    def __str__(self):
        status = "✓" if self.connected else "✗"
        return f"{status} {self.alumno} → {self.provider}"
    
    def mark_connected(self, athlete_id: str, expires_at=None):
        """Mark integration as successfully connected."""
        self.connected = True
        self.athlete_id = str(athlete_id)
        self.expires_at = expires_at
        self.error_reason = ""
        self.error_message = ""
        self.last_error_at = None
        self.save()
    
    def mark_failed(self, error_reason: str, error_message: str = ""):
        """Mark integration as failed with specific reason."""
        self.connected = False
        self.error_reason = str(error_reason)[:60]
        self.error_message = str(error_message)
        self.last_error_at = timezone.now()
        self.save()
