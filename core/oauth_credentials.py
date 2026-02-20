"""
OAuth Credentials Bridge - P0 Implementation

Purpose:
    Persist OAuth tokens from custom callback to django-allauth models (SocialAccount/SocialToken)
    for backward compatibility with obtener_cliente_strava_para_alumno().

Design:
    P0: Write to allauth (SocialAccount + SocialToken)
    Future: Migrate to custom OAuthCredential model for provider-agnostic storage

Security:
    - Tokens NEVER logged
    - Multi-tenant safe (token bound to Alumno.usuario)
    - Fail-closed (missing SocialApp or user → error, not silent failure)
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone
from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class PersistResult:
    """Result of persist_oauth_tokens operation"""
    success: bool
    error_reason: str = ""
    error_message: str = ""


def persist_oauth_tokens(
    *,
    provider: str,
    user: User,
    external_user_id: str,
    access_token: str,
    refresh_token: str,
    expires_at: Optional[datetime] = None,
    extra_data: Optional[dict] = None,
) -> PersistResult:
    """
    P0 Bridge: Persist OAuth credentials to django-allauth models.
    
    This enables backward compatibility with obtener_cliente_strava_para_alumno()
    which queries SocialToken.objects.filter(account__user=user, account__provider='strava').
    
    Future: Replace with custom OAuthCredential model for provider-agnostic storage.
    
    Args:
        provider: Provider ID (e.g., 'strava', 'garmin')
        user: Django User (must be Alumno.usuario)
        external_user_id: Provider's user ID (e.g., Strava athlete_id)
        access_token: OAuth access token (NEVER logged)
        refresh_token: OAuth refresh token (NEVER logged)
        expires_at: Token expiration (timezone-aware datetime, optional)
        extra_data: Optional profile data (sanitized, no tokens)
    
    Returns:
        PersistResult(success=True/False, error_reason=..., error_message=...)
    
    Side Effects:
        - Creates/updates SocialAccount
        - Creates/updates SocialToken
    
    Security:
        - Tokens NEVER logged (only flags: has_access_token, has_refresh_token)
        - extra_data sanitized (no tokens)
        - Multi-tenant safe (token bound to user)
    """
    # Validate inputs
    if not provider:
        return PersistResult(False, "invalid_provider", "Provider cannot be empty")
    
    if not user or not user.id:
        return PersistResult(False, "invalid_user", "User must be a persisted Django User")
    
    if not external_user_id:
        return PersistResult(False, "invalid_external_user_id", "External user ID cannot be empty")
    
    if not access_token:
        return PersistResult(False, "invalid_access_token", "Access token cannot be empty")
    
    # Ensure expires_at is timezone-aware if provided
    if expires_at and timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, timezone=timezone.utc)
    
    # Lookup SocialApp (required for SocialToken)
    try:
        social_app = SocialApp.objects.filter(provider=provider).first()
        if not social_app:
            logger.error("oauth.credentials.missing_socialapp", extra={
                "provider": provider,
                "user_id": user.id,
            })
            return PersistResult(
                False,
                "missing_socialapp",
                f"{provider.capitalize()} SocialApp not configured. Run: python manage.py strava_oauth_doctor --fix-sites"
            )
    except Exception as e:
        logger.exception("oauth.credentials.socialapp_lookup_failed", extra={
            "provider": provider,
            "user_id": user.id,
            "error": str(e),
        })
        return PersistResult(False, "socialapp_lookup_error", f"Failed to lookup SocialApp: {str(e)}")
    
    try:
        # Create/update SocialAccount
        social_account, account_created = SocialAccount.objects.update_or_create(
            user=user,
            provider=provider,
            defaults={
                "uid": str(external_user_id),
                "extra_data": extra_data or {},
            }
        )
        
        # Create/update SocialToken
        social_token, token_created = SocialToken.objects.update_or_create(
            account=social_account,
            app=social_app,
            defaults={
                "token": access_token,
                "token_secret": refresh_token or "",
                "expires_at": expires_at,
            }
        )
        
        # Log success (NO tokens, only flags)
        logger.info("oauth.credentials.persist_success", extra={
            "provider": provider,
            "user_id": user.id,
            "external_user_id": external_user_id,
            "account_created": account_created,
            "token_created": token_created,
            "has_access_token": bool(access_token),
            "has_refresh_token": bool(refresh_token),
            "has_expires_at": expires_at is not None,
        })
        
        return PersistResult(success=True)
        
    except Exception as e:
        logger.exception("oauth.credentials.persist_failed", extra={
            "provider": provider,
            "user_id": user.id,
            "external_user_id": external_user_id,
            "error": str(e),
        })
        return PersistResult(False, "persist_error", f"Failed to persist credentials: {str(e)}")


def persist_oauth_tokens_v2(
    *,
    provider: str,
    alumno,
    token_data: dict,
    external_user_id: str,
) -> PersistResult:
    """
    Provider-agnostic upsert of OAuthCredential (PR10 foundation).

    This function is the future storage path for non-Strava providers
    (Garmin, Coros, Suunto, Polar, Wahoo). It stores tokens in the
    OAuthCredential model and does NOT touch allauth SocialToken/SocialAccount.

    Strava continues using persist_oauth_tokens() above, unchanged.

    Args:
        provider:         Provider ID (e.g., 'garmin', 'coros'). Lowercased/stripped.
        alumno:           Alumno model instance (must be persisted, i.e. have .pk).
        token_data:       Dict that MUST contain 'access_token'.
                          Optional keys: 'refresh_token' (str), 'expires_at' (datetime).
        external_user_id: Provider's UID for this user. Cannot be empty.

    Returns:
        PersistResult(success=True/False, error_reason=..., error_message=...)

    Idempotency:
        Repeated calls with the same (alumno, provider) update the existing row.
        Concurrency-safe: uses transaction.atomic + select_for_update on re-fetch
        if a race-condition IntegrityError occurs.

    Security:
        Tokens NEVER logged (only boolean flags: has_access_token, has_refresh_token).
        Multi-tenant: the credential is bounded to alumno (organisation-scoped).
    """
    from django.db import IntegrityError, transaction

    # --- Input validation ---
    if not provider or not isinstance(provider, str):
        return PersistResult(False, "invalid_provider", "Provider cannot be empty")

    provider = provider.lower().strip()

    if not provider:
        return PersistResult(False, "invalid_provider", "Provider cannot be empty after normalisation")

    if alumno is None or not getattr(alumno, "pk", None):
        return PersistResult(False, "invalid_alumno", "Alumno must be a persisted Alumno instance")

    if not isinstance(token_data, dict):
        return PersistResult(False, "invalid_token_data", "token_data must be a dict")

    access_token = token_data.get("access_token", "")
    if not access_token:
        return PersistResult(False, "invalid_access_token", "token_data must contain a non-empty 'access_token'")

    if not external_user_id:
        return PersistResult(False, "invalid_external_user_id", "external_user_id cannot be empty")

    refresh_token = token_data.get("refresh_token", "") or ""
    expires_at = token_data.get("expires_at", None)

    # Normalise expires_at to timezone-aware
    if expires_at and timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, timezone=timezone.utc)

    # --- Upsert (concurrency-safe) ---
    try:
        with transaction.atomic():
            from core.models import OAuthCredential  # local import avoids circular deps

            obj, created = OAuthCredential.objects.update_or_create(
                alumno=alumno,
                provider=provider,
                defaults={
                    "external_user_id": str(external_user_id),
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at,
                },
            )

        logger.info(
            "oauth_credentials_v2.persist_success",
            extra={
                "provider": provider,
                "alumno_id": alumno.pk,
                "external_user_id": external_user_id,
                "created": created,
                "has_access_token": True,
                "has_refresh_token": bool(refresh_token),
                "has_expires_at": expires_at is not None,
            },
        )
        return PersistResult(success=True)

    except IntegrityError:
        # Race condition: another concurrent request already created the row.
        # Re-fetch and update explicitly within a new atomic block.
        try:
            with transaction.atomic():
                from core.models import OAuthCredential  # noqa: F811

                obj = OAuthCredential.objects.select_for_update().get(
                    alumno=alumno, provider=provider
                )
                obj.external_user_id = str(external_user_id)
                obj.access_token = access_token
                obj.refresh_token = refresh_token
                obj.expires_at = expires_at
                obj.save(update_fields=["external_user_id", "access_token", "refresh_token", "expires_at", "updated_at"])

            logger.info(
                "oauth_credentials_v2.persist_race_resolved",
                extra={
                    "provider": provider,
                    "alumno_id": alumno.pk,
                    "has_access_token": True,
                },
            )
            return PersistResult(success=True)

        except Exception as inner_exc:
            logger.exception(
                "oauth_credentials_v2.persist_race_failed",
                extra={
                    "provider": provider,
                    "alumno_id": alumno.pk,
                    "error": str(inner_exc),
                },
            )
            return PersistResult(False, "persist_race_error", f"Race resolution failed: {str(inner_exc)}")

    except Exception as exc:
        logger.exception(
            "oauth_credentials_v2.persist_failed",
            extra={
                "provider": provider,
                "alumno_id": alumno.pk,
                "error": str(exc),
            },
        )
        return PersistResult(False, "persist_error", f"Failed to persist OAuthCredential: {str(exc)}")

