import math
from datetime import timedelta, date

# ==============================================================================
#  1. UTILIDADES BÁSICAS
# ==============================================================================
def calcular_pendiente(distancia_m, desnivel_m):
    if not distancia_m or distancia_m <= 0: return 0.0
    return (desnivel_m / distancia_m) * 100

def pace_a_velocidad(ritmo_seg_km):
    if not ritmo_seg_km or ritmo_seg_km <= 0: return 0
    return 3600 / ritmo_seg_km

def velocidad_a_pace(velocidad_kmh):
    if not velocidad_kmh or velocidad_kmh <= 0: return 0
    return 3600 / velocidad_kmh

def segundos_a_formato_tiempo(segundos):
    if not segundos or segundos <= 0: return "-"
    return str(timedelta(seconds=int(segundos)))

# ==============================================================================
#  2. CÁLCULOS DE CARGA Y TRAIL
# ==============================================================================
def calcular_gap_minetti(ritmo_seg_km, pendiente_porcentaje):
    if not ritmo_seg_km or ritmo_seg_km <= 0: return 0
    g = pendiente_porcentaje / 100.0
    costo_w = (155.4 * (g**5)) - (30.4 * (g**4)) - (43.3 * (g**3)) + (46.3 * (g**2)) + (19.5 * g) + 3.6
    factor = max(0.5, min(costo_w / 3.6, 5.0))
    return ritmo_seg_km / factor

def calcular_tss_gap(tiempo_min, gap_seg_km, umbral_ritmo_seg_km):
    if not tiempo_min or not gap_seg_km or gap_seg_km <= 0: return 0, 0
    ftp_pace = umbral_ritmo_seg_km if umbral_ritmo_seg_km > 0 else 250 
    intensity_factor = ftp_pace / gap_seg_km
    duracion_seg = tiempo_min * 60
    rtss = (duracion_seg * (intensity_factor ** 2)) / 3600 * 100
    return round(rtss, 1), round(intensity_factor, 2)

def calcular_trimp(tiempo_min, avg_hr, max_hr, rest_hr, es_hombre=True):
    if not tiempo_min or not avg_hr or not max_hr or max_hr <= rest_hr: return 0 
    hrr_fraction = (avg_hr - rest_hr) / (max_hr - rest_hr)
    factor_genero = 1.92 if es_hombre else 1.67
    try: return round(tiempo_min * hrr_fraction * 0.64 * math.exp(factor_genero * hrr_fraction), 1)
    except: return 0

def calcular_tss_power(tiempo_min, avg_power, ftp):
    if not tiempo_min or not avg_power or not ftp or ftp == 0: return 0, 0
    intensity_factor = avg_power / ftp
    return round(((tiempo_min * 60) * avg_power * intensity_factor) / (ftp * 3600) * 100, 1), round(intensity_factor, 2)

def calcular_load_rpe(tiempo_min, rpe):
    if not tiempo_min or not rpe: return 0
    return round(tiempo_min * rpe, 1)

def determinar_carga_final(tss_power, tss_gap, trimp, rpe_load):
    if tss_power and tss_power > 0: return tss_power
    if tss_gap and tss_gap > 0: return tss_gap
    if trimp and trimp > 0: return trimp
    return rpe_load

# ==============================================================================
#  3. ESTIMACIÓN AUTOMÁTICA DE VAM (TESTS DE CAMPO)
# ==============================================================================
def calcular_vam_desde_tests(cooper_km=0, tiempo_1k=None, tiempo_5k=None):
    """
    Calcula la VAM basándose en resultados de tests de campo.
    Ajustado para atletas competitivos (factores dinámicos).
    """
    estimaciones = []

    # 1. Test de Cooper (12 min) -> Distancia * 5 = km/h
    if cooper_km and cooper_km > 0:
        vam_cooper = cooper_km * 5
        estimaciones.append(vam_cooper)

    # 2. Test 5K Llano
    if tiempo_5k:
        try:
            segundos = tiempo_5k.total_seconds()
            if segundos > 0:
                velocidad_5k_kmh = (5.0 / segundos) * 3600
                # Ajuste Pro: Si corre sub-20' (15km/h), es más eficiente (95% VAM)
                # Si es amateur, es menos eficiente (93% VAM)
                factor = 0.95 if velocidad_5k_kmh >= 15 else 0.93
                vam_5k = velocidad_5k_kmh / factor
                estimaciones.append(vam_5k)
        except: pass

    # 3. Test 1K (Tolerancia al Lactato)
    if tiempo_1k:
        try:
            segundos = tiempo_1k.total_seconds()
            if segundos > 0:
                velocidad_1k_kmh = (1.0 / segundos) * 3600
                # Ajuste Pro: Si corre sub-3:20 (18km/h), factor 1.05 (muy eficiente)
                # Si es amateur, factor 1.12 (menos tolerancia)
                factor = 1.05 if velocidad_1k_kmh >= 18 else 1.12
                vam_1k = velocidad_1k_kmh / factor
                estimaciones.append(vam_1k)
        except: pass

    # Devolvemos la estimación más alta (el techo fisiológico demostrado)
    if estimaciones:
        return round(max(estimaciones), 1)
    
    return 0

# ==============================================================================
#  4. CALCULADORA DE RITMOS DE SERIES (NUEVO)
# ==============================================================================
def calcular_ritmos_series(vam_kmh):
    """
    Calcula los ritmos objetivo para series fraccionadas basados en la VAM.
    Retorna un diccionario con los tiempos esperados (String formateado).
    """
    if not vam_kmh or vam_kmh <= 0: return None

    # Coeficientes de Intensidad (% de VAM)
    # Series cortas se corren >100% VAM (Anaeróbico), largas <100% (VO2max/Umbral)
    coeficientes = {
        '100m': 1.20,  # 120% VAM (Velocidad pura)
        '200m': 1.15,  # 115% VAM
        '250m': 1.12,
        '400m': 1.10,  # 110% VAM (Clásico VO2max corto)
        '500m': 1.08,
        '800m': 1.03,  # 103% VAM
        '1000m': 1.00, # 100% VAM (Referencia)
        '1200m': 0.98,
        '1600m': 0.96, # La milla
        '2000m': 0.92, # 92% VAM (Umbral Anaeróbico)
    }

    ritmos = {}
    
    for dist_str, factor in coeficientes.items():
        # 1. Velocidad objetivo
        vel_objetivo = vam_kmh * factor
        # 2. Ritmo por km (seg/km)
        pace_seg_km = velocidad_a_pace(vel_objetivo)
        # 3. Tiempo para la distancia específica
        distancia_m = int(dist_str.replace('m', ''))
        tiempo_seg = pace_seg_km * (distancia_m / 1000)
        
        # Formatear mm:ss o s.ms
        m, s = divmod(int(tiempo_seg), 60)
        if m == 0:
            ritmos[dist_str] = f"{s}''" # Ej: 45''
        else:
            ritmos[dist_str] = f"{m}'{s:02d}''" # Ej: 3'45''

    return ritmos

# ==============================================================================
#  5. PREDICCIONES Y SIMULADOR
# ==============================================================================
def predecir_tiempo_riegel(dist_obj, dist_test, tiempo_test, exponente=1.06):
    if not dist_test or not tiempo_test: return 0
    return int(tiempo_test * ((dist_obj / dist_test) ** exponente))

def generar_pronosticos_alumno(vam_kmh):
    if not vam_kmh or vam_kmh <= 0: return tuple([None]*9)
    dist_test, tiempo_test = 2.0, (velocidad_a_pace(vam_kmh) * 2.0)
    
    p10 = predecir_tiempo_riegel(10, dist_test, tiempo_test)
    p21 = predecir_tiempo_riegel(21.097, dist_test, tiempo_test)
    p42 = predecir_tiempo_riegel(42.195, dist_test, tiempo_test)
    
    def calc_trail(km, d_plus, exp=1.10):
        return predecir_tiempo_riegel(km + (d_plus/100), dist_test, tiempo_test, exp)

    return (
        segundos_a_formato_tiempo(p10), segundos_a_formato_tiempo(p21), segundos_a_formato_tiempo(p42),
        segundos_a_formato_tiempo(calc_trail(21, 1000)), segundos_a_formato_tiempo(calc_trail(42, 2000)),
        segundos_a_formato_tiempo(calc_trail(60, 3000)), segundos_a_formato_tiempo(calc_trail(80, 4000)),
        segundos_a_formato_tiempo(calc_trail(100, 5000)), segundos_a_formato_tiempo(calc_trail(160, 8000, 1.12))
    )

# ==============================================================================
#  6. CALCULADORA DE PERIODIZACIÓN (VOLUMEN EN EL TIEMPO)
# ==============================================================================
def calcular_periodizacion_volumen(km_esfuerzo, fecha_carrera):
    if not fecha_carrera: return "Sin fecha"
    
    factor_volumen = 1.5 if km_esfuerzo < 42 else (1.1 if km_esfuerzo < 100 else 0.75)
    objetivo_km = int(km_esfuerzo * factor_volumen)
    
    # --- CÁLCULO DE HORAS (NUEVO) ---
    # Asumimos un ritmo de entrenamiento suave promedio para Trail (ej: 9 km/h o 6:40 min/km)
    ritmo_promedio_entreno = 9.0 
    objetivo_horas = objetivo_km / ritmo_promedio_entreno
    
    hoy = date.today()
    dias_para_carrera = (fecha_carrera - hoy).days
    fecha_pico = fecha_carrera - timedelta(weeks=3)
    
    fase = ""
    consejo = ""
    
    if dias_para_carrera < 0: return "🏁 Carrera finalizada."
    elif dias_para_carrera < 21:
        fase = "Tapering (Descarga)"
        consejo = "📉 Reduce volumen al 50-70%. Descansa."
    elif dias_para_carrera < 60:
        fase = "Específica / Pico"
        consejo = f"🔥 Estás en la fase dura. Busca llegar a {objetivo_km}km pronto."
    elif dias_para_carrera < 120:
        fase = "Construcción (Build)"
        consejo = "📈 Aumenta 10% semanal progresivo."
    else:
        fase = "Base Aeróbica"
        consejo = "🟢 Volumen bajo/medio. Prioriza fuerza y técnica."

    return (
        f"📅 Planificación Temporal:\n"
        f"• Meta Pico: ~{objetivo_km} km/sem (Esfuerzo).\n"
        f"• Horas Pico: ~{int(objetivo_horas)}h {int((objetivo_horas%1)*60)}m semanales.\n" # <--- NUEVO
        f"• Fecha Pico: Semana del {fecha_pico.strftime('%d/%m/%Y')} (3 sem antes).\n"
        f"• Fase Actual: {fase}.\n"
        f"• Consejo IA: {consejo}"
    )

def simular_carrera_integral(distancia_km, desnivel_pos_m, factor_terreno, alumno, fecha_carrera=None):
    vam = alumno.vam_actual
    peso = alumno.peso
    pref_comida = getattr(alumno, 'preferencia_alimentacion', 'MIX') 
    
    if not vam or vam <= 0: return None, "Faltan datos de VAM.", None

    km_esfuerzo = distancia_km + (desnivel_pos_m / 100)
    ritmo_vam = velocidad_a_pace(vam)
    tiempo_base = predecir_tiempo_riegel(km_esfuerzo, 2.0, ritmo_vam * 2.0, 1.06)
    tiempo_final_seg = tiempo_base * factor_terreno
    horas = tiempo_final_seg / 3600
    
    cho_hora = 30 if horas < 1.5 else (45 if horas < 3 else (60 if horas < 5 else 75))
    liquido_hora = 500 + ((peso - 60) * 5)
    total_cho = int(cho_hora * horas)
    total_litros = (liquido_hora * horas) / 1000

    fuentes_cho = ""
    if pref_comida == 'GELES': fuentes_cho = f"⚡ {int(cho_hora/25)} geles/hora."
    elif pref_comida == 'REAL': fuentes_cho = f"🍎 {int(cho_hora/20)} pasas/dátiles/membrillo por hora."
    else: fuentes_cho = f"🔄 {int(cho_hora/25)} gel/h + pasas/membrillo."

    reporte_nutricional = (
        f"🏁 CARRERA ({segundos_a_formato_tiempo(tiempo_final_seg)})\n"
        f"• Comer: {cho_hora}g CHO/h ({total_cho}g total). {fuentes_cho}\n"
        f"• Beber: {int(liquido_hora)}ml/h ({total_litros:.1f}L total)."
    )

    reporte_volumen = calcular_periodizacion_volumen(km_esfuerzo, fecha_carrera)
    
    return segundos_a_formato_tiempo(tiempo_final_seg), reporte_nutricional, reporte_volumen