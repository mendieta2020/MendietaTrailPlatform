from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class InjuryRiskResult:
    risk_level: str  # LOW | MEDIUM | HIGH
    risk_score: int  # 0–100
    risk_reasons: List[str]


def _clamp_int(n: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(n))))


def _escalate(level: str, steps: int = 1) -> str:
    order = ["LOW", "MEDIUM", "HIGH"]
    try:
        idx = order.index(level)
    except ValueError:
        idx = 0
    return order[min(len(order) - 1, idx + steps)]


def compute_injury_risk(
    *,
    ctl: float,
    atl: float,
    tsb: float,
    atl_7d_ago: Optional[float] = None,
    last_3_days_tss: Optional[Iterable[float]] = None,
    high_tss_threshold: float = 100.0,
    high_load_relative_to_ctl: float = 1.5,
) -> InjuryRiskResult:
    """
    Motor de riesgo de lesión (v1) basado en métricas PMC.

    Reglas:
    - Base por TSB:
      - TSB < -30 -> HIGH
      - -30 <= TSB < -10 -> MEDIUM
      - TSB >= -10 -> LOW
    - Factor: ATL creciendo rápido (> +20% en 7 días) -> subir 1 nivel
    - Factor: 3+ días consecutivos de carga alta -> subir 1 nivel
      (v1: carga alta si TSS diario >= max(high_tss_threshold, high_load_relative_to_ctl*CTL))

    Score:
    - Base: LOW 25, MEDIUM 60, HIGH 85
    - +10 por cada factor aplicado (clamp 0–100)
    """

    reasons: List[str] = []

    # 1) Base por TSB
    if tsb < -30:
        level = "HIGH"
        base_score = 85
        reasons.append("TSB < -30 (muy negativo): fatiga alta vs fitness")
    elif tsb < -10:
        level = "MEDIUM"
        base_score = 60
        reasons.append("TSB entre -30 y -10: fatiga elevada")
    else:
        level = "LOW"
        base_score = 25
        reasons.append("TSB >= -10: forma aceptable")

    score = float(base_score)

    # 2) Factor: ATL creciendo rápido (>20% en 7 días)
    grew_fast = False
    if atl_7d_ago is not None and atl_7d_ago > 0:
        if atl > (atl_7d_ago * 1.2):
            grew_fast = True
            level = _escalate(level, 1)
            score += 10
            reasons.append("ATL creció >20% en 7 días")

    # 3) Factor: 3+ días consecutivos de carga alta
    consecutive_high = False
    if last_3_days_tss is not None:
        tss_list = list(last_3_days_tss)
        if len(tss_list) >= 3:
            threshold = max(float(high_tss_threshold), float(high_load_relative_to_ctl) * float(ctl))
            if all((t or 0) >= threshold for t in tss_list[:3]):
                consecutive_high = True
                level = _escalate(level, 1)
                score += 10
                reasons.append(f"3+ días consecutivos con carga alta (TSS >= {threshold:.0f})")

    return InjuryRiskResult(
        risk_level=level,
        risk_score=_clamp_int(score),
        risk_reasons=reasons,
    )

