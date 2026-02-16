def calcular_porcentaje_cumplimiento(entrenamiento) -> int:
    """
    Calcula el porcentaje de cumplimiento de un entrenamiento.
    Regla de Negocio (PR5): cap fijo 120%, prioridad Distancia > Tiempo.
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

    # Business Rules: Floor 0, Cap 120
    final_score = int(min(max(ratio, 0.0), 120.0))
    return final_score
