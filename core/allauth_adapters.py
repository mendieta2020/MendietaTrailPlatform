import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

logger = logging.getLogger("allauth.socialaccount")


def _safe_str(v, max_len: int = 200) -> str:
    try:
        s = str(v)
    except Exception:
        return "<unprintable>"
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


class LoggingSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    allauth suele mostrar "Third-Party Login Failure" cuando algo falla en OAuth
    (state mismatch, invalid_grant, redirect_uri mismatch, invalid_client, etc).

    Este adapter fuerza logging con traceback completo + contexto sanitizado.
    """

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        provider_id = getattr(provider, "id", None) or getattr(provider, "provider_id", None) or _safe_str(provider)

        # Sanitizar query params (no loguear code completo).
        get = getattr(request, "GET", {})
        code = get.get("code")
        state = get.get("state")
        err = get.get("error") or error

        ctx = {
            "path": getattr(request, "path", None),
            "provider": provider_id,
            "error": _safe_str(err),
            "has_code": bool(code),
            "code_len": (len(code) if code else 0),
            "state_prefix": (state[:8] + "..." if isinstance(state, str) and len(state) > 8 else state),
        }

        if exception:
            # logger.exception incluye traceback del exception actual.
            logger.exception("Social authentication error (details=%s)", ctx)
        else:
            logger.error("Social authentication error without exception (details=%s)", ctx)

        return super().on_authentication_error(
            request,
            provider=provider,
            error=error,
            exception=exception,
            extra_context=extra_context,
        )

