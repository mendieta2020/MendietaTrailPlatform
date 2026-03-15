"""
backend package.

Importa la app de Celery si está disponible. Esto evita que comandos de Django
como `manage.py migrate` o `manage.py shell` fallen en entornos donde Celery
no está instalado (por ejemplo, en setups mínimos o CI).
"""

from __future__ import annotations

from typing import Optional

celery_app = None  # type: Optional[object]

try:
    # Import lazy: si Celery no está instalado, no bloqueamos comandos de Django.
    from .celery import app as celery_app  # noqa: F401
except ModuleNotFoundError as e:
    # Solo ignoramos el caso "celery" faltante; otros módulos faltantes deben fallar.
    if getattr(e, "name", None) != "celery":
        raise

__all__ = ("celery_app",)