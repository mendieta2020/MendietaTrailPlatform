/**
 * Helper de compatibilidad para respuestas "legacy" (lista plana)
 * y "nueva arquitectura" (DRF PageNumberPagination => { count, next, previous, results }).
 *
 * Acepta:
 * - data (res.data)
 * - response (axios response completo)
 */
export function unpackResults(payload) {
  const data = payload && payload.data !== undefined ? payload.data : payload;

  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;

  // Fallback defensivo: algunos endpoints pueden devolver null/undefined
  return [];
}

