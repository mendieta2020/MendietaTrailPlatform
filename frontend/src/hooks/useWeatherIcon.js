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
