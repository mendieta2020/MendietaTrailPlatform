from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#
# Python stdlib logging raises:
#   KeyError: "Attempt to overwrite '<attr>' in LogRecord"
# when `extra={...}` includes reserved LogRecord attribute names.
#

RESERVED_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    {
        "created",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "name",
    }
)


def safe_extra(extra: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Return a copy of `extra` safe for stdlib logging.

    - Casts keys to str
    - Renames reserved LogRecord attribute keys by prefixing them with `log_`
    - Avoids overwriting keys if collisions occur
    """
    if not extra:
        return {}

    out: dict[str, Any] = {}
    for k, v in extra.items():
        key = str(k)
        if key in RESERVED_LOGRECORD_ATTRS:
            key = f"log_{key}"

        # Avoid collisions (incl. if caller already had log_* keys).
        if key in out:
            base = key
            i = 1
            while key in out:
                key = f"{base}_{i}"
                i += 1

        out[key] = v
    return out


_SENSITIVE_KEYS = {
    "client_secret",
    "refresh_token",
    "access_token",
    "authorization",
    "code",
    "token",
    "password",
}

def sanitize_secrets(obj: Any) -> Any:
    """
    Sanitize payloads/kwargs: redact secrets, truncate long strings.
    """
    if obj is None:
        return None

    if isinstance(obj, (int, float, bool)):
        return obj

    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return "<binary>"

    if isinstance(obj, str):
        if len(obj) > 400:
            return obj[:397] + "..."
        return obj

    if isinstance(obj, list):
        return [sanitize_secrets(x) for x in obj[:50]]

    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:200]:
            if str(k).lower() in _SENSITIVE_KEYS:
                out[k] = "REDACTED"
            else:
                out[k] = sanitize_secrets(v)
        return out

    return str(obj)[:200]

