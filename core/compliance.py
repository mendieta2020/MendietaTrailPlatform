def calcular_porcentaje_cumplimiento(entrenamiento) -> int:
    """
    Calcula el porcentaje de cumplimiento de un entrenamiento.
    Regla de Negocio (ADR-004): cap 150%, >150 devuelve 151 (⚠️ Exceso). Prioridad Distancia > Tiempo.
    Floor 0%. Safe division.
    """
    if not entrenamiento.completado:
        return 0

    ratio = 0.0
    
    # Priority A: Distance
    # Usamos valores float para el cálculo para evitar problemas de tipos mixtos (Decimal vs float)
    plan_dist = float(entrenamiento.distancia_planificada_km or 0.0)
    if plan_dist > 0:
        real_dist = float(entrenamiento.distancia_real_km or 0.0)
        ratio = (real_dist / plan_dist) * 100.0
    
    # Priority B: Time (if no planned distance)
    else:
        plan_time = float(entrenamiento.tiempo_planificado_min or 0.0)
        if plan_time > 0:
            real_time = float(entrenamiento.tiempo_real_min or 0.0)
            ratio = (real_time / plan_time) * 100.0
        # Priority C: Freestyle (No plan limits) -> 100% if completed
        else:
             return 100

    # Business Rules: Floor 0, Cap 150 (ADR-004); >150 = ⚠️ Exceso sentinel
    if ratio > 150.0:
        return 151
    final_score = int(min(max(ratio, 0.0), 150.0))
    return final_score
