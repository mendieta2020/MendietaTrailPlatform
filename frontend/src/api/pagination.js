// Helpers para endpoints DRF paginados (count/next/previous/results)
// Back-compat: si el backend devuelve un array "plano", también funciona.

export function unpackResults(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

export function unpackCount(data) {
  if (typeof data?.count === 'number') return data.count;
  const results = unpackResults(data);
  return results.length;
}

