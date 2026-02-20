from __future__ import annotations

from typing import Iterable, Sequence


def smooth_altitude(values: Sequence[float], window: int = 3) -> list[float]:
    """
    Smoothing simple (media móvil) para reducir ruido de altitud.
    window=3 => promedio de [i-1, i, i+1] (clamped).
    """
    if not values:
        return []
    if window <= 1:
        return [float(v) for v in values]

    half = window // 2
    out: list[float] = []
    n = len(values)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(float(x) for x in chunk) / float(len(chunk)))
    return out


def compute_elevation_loss_m(altitude_stream_m: Iterable[float] | None) -> float | None:
    """
    Calcula elev_loss (m) como sumatoria de descensos consecutivos.
    - Si no hay stream o tiene <2 puntos => None (faltante).
    - Aplica smoothing simple para evitar micro-oscilaciones.
    """
    if altitude_stream_m is None:
        return None
    values = [float(v) for v in altitude_stream_m if v is not None]
    if len(values) < 2:
        return None

    smoothed = smooth_altitude(values, window=3)
    loss = 0.0
    prev = smoothed[0]
    for cur in smoothed[1:]:
        if cur < prev:
            loss += (prev - cur)
        prev = cur

    # Redondeo conservador (1 decimal) para estabilidad + evitar ruido
    return round(float(loss), 1)
