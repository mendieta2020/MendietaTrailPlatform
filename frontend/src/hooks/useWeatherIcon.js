/**
 * useWeatherIcon.js
 *
 * PR-145d: Utility to convert an OWM weather_snapshot (from WorkoutAssignment)
 * into a display chip string: emoji + temperature.
 *
 * This is NOT a React hook — it's a pure utility exported as a named function.
 * The file name follows project convention for the hooks/ directory.
 */

const OWM_ICON_MAP = {
  '01': '☀️',
  '02': '⛅',
  '03': '☁️',
  '04': '☁️',
  '09': '🌧️',
  '10': '🌧️',
  '11': '⛈️',
  '13': '🌨️',
  '50': '🌫️',
};

/**
 * Returns a compact weather chip string from an OWM snapshot, or null.
 *
 * @param {Object|null} snapshot - weather_snapshot from WorkoutAssignment
 * @returns {string|null} e.g. '🌧️ 12°C' or null
 */
export function weatherChip(snapshot) {
  if (!snapshot || snapshot.temp_c == null) return null;

  const code = snapshot.icon ? snapshot.icon.slice(0, 2) : null;
  const emoji = (code && OWM_ICON_MAP[code]) || '🌡️';

  return `${emoji} ${snapshot.temp_c}°C`;
}

/**
 * PR-179b: Returns { icon, label, alert } for a weather snapshot.
 * alert is non-null when conditions exceed comfort thresholds.
 *
 * @param {Object|null} snapshot
 * @returns {{ icon: string, label: string, alert: string|null } | null}
 */
export function weatherBadgeProps(snapshot) {
  if (!snapshot || snapshot.temp_c == null) return null;

  const { temp_c, precipitation_pct = 0, wind_kmh = 0, icon } = snapshot;
  const code = icon ? icon.slice(0, 2) : '01';
  const baseIcon = OWM_ICON_MAP[code] || '🌡️';

  if (temp_c < 5)              return { icon: '🥶', label: `${temp_c}°C`, alert: 'Frío extremo — abrigate' };
  if (temp_c > 32)             return { icon: '🔥', label: `${temp_c}°C`, alert: 'Calor extremo — extrema hidratación' };
  if (precipitation_pct > 70)  return { icon: '🌧️', label: `${temp_c}°C`, alert: 'Alta probabilidad de lluvia' };
  if (precipitation_pct > 30)  return { icon: '⛅', label: `${temp_c}°C`, alert: 'Posible lluvia' };
  if (wind_kmh > 30)           return { icon: '💨', label: `${temp_c}°C`, alert: 'Viento fuerte' };
  return { icon: baseIcon, label: `${temp_c}°C`, alert: null };
}
