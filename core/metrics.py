import math

def calcular_load_rpe(tiempo_min, rpe):
    """
    Carga Subjetiva (Escala de Foster).
    Input: Tiempo en minutos, RPE (1-10)
    Output: Unidades arbitrarias de carga.
    """
    if not tiempo_min or not rpe:
        return 0
    # Normalizamos por si el RPE viene en otra escala, aseguramos max 10
    rpe_ajustado = min(rpe, 10) 
    return round(tiempo_min * rpe_ajustado, 1)

def calcular_trimp(tiempo_min, avg_hr, max_hr, rest_hr, es_hombre=True):
    """
    Calcula el TRIMP (Training Impulse) usando la fórmula exponencial de Banister.
    Esta es la métrica reina para deportes de resistencia basada en pulso.
    """
    if not tiempo_min or not avg_hr or not max_hr:
        return 0
    
    if max_hr <= rest_hr: 
        return 0 # Datos de alumno mal configurados

    # 1. Reserva de Frecuencia Cardíaca (HRR)
    # ¿A qué % de su motor real trabajó?
    hrr_fraction = (avg_hr - rest_hr) / (max_hr - rest_hr)
    
    # 2. Factor de género (Los hombres acumulan lactato distinto a las mujeres)
    # y = 1.92 (Hombres), 1.67 (Mujeres)
    factor_genero = 1.92 if es_hombre else 1.67
    
    # 3. Fórmula Banister
    try:
        trimp = tiempo_min * hrr_fraction * 0.64 * math.exp(factor_genero * hrr_fraction)
        return round(trimp, 2)
    except Exception:
        return 0

def calcular_tss_estimado(tiempo_min, avg_power, ftp):
    """
    Calcula TSS (Training Stress Score) y IF (Intensity Factor).
    Usamos Potencia Promedio. (El TSS 'Real' usa Potencia Normalizada, 
    que implementaremos cuando procesemos el archivo .FIT segundo a segundo).
    """
    if not tiempo_min or not avg_power or not ftp or ftp == 0:
        return 0, 0 # TSS=0, IF=0

    # 1. Factor de Intensidad (IF)
    # 1.0 = Ir al umbral (FTP). 0.7 = Aeróbico suave.
    intensity_factor = avg_power / ftp
    
    # 2. Fórmula TSS de Coggan
    # (Segundos * Watts * IF) / (FTP * 3600) * 100
    tiempo_sec = tiempo_min * 60
    tss = (tiempo_sec * avg_power * intensity_factor) / (ftp * 3600) * 100
    
    return round(tss, 2), round(intensity_factor, 2)

def determinar_carga_final(tss, trimp, rpe_load):
    """
    Lógica de Cascada: ¿Qué número es el más fiable?
    1. Potencia (TSS) -> Es un dato mecánico objetivo (Rey).
    2. Corazón (TRIMP) -> Es un dato fisiológico objetivo (Príncipe).
    3. RPE -> Es subjetivo, pero mejor que nada (Comodín).
    """
    if tss and tss > 0:
        return tss
    if trimp and trimp > 0:
        return trimp
    return rpe_load