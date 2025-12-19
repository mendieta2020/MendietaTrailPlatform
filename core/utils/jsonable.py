from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def to_jsonable(obj: Any):
    """
    Convierte un objeto arbitrario a algo JSON-serializable (safe para JSONField / json.dumps).

    Reglas:
    - dict/list/tuple/set: recursivo
    - datetime/date: isoformat()
    - Decimal: str() (no perder precisión)
    - UUID: str()
    - fallback: str(obj)
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return str(obj)

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, dict):
        # JSON exige keys string; si viene algo raro, lo casteamos.
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]

    return str(obj)

