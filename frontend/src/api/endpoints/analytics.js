import client from '../client';

function addParam(params, key, value) {
  if (value === undefined || value === null || value === '') return;
  params[key] = value;
}

/**
 * @typedef {Object} GetAlertsParams
 * @property {number=} page
 * @property {number=} pageSize
 * @property {number|string=} alumnoId
 * @property {boolean=} vistoPorCoach
 * @property {AbortSignal=} signal
 */

/**
 * DRF: GET /api/analytics/alerts/
 * Query params:
 * - page, page_size
 * - alumno_id
 * - visto_por_coach
 *
 * @param {GetAlertsParams} params
 */
export async function getAlerts({ page, pageSize, alumnoId, vistoPorCoach, signal } = {}) {
  const query = {};
  addParam(query, 'page', page);
  addParam(query, 'page_size', pageSize);
  addParam(query, 'alumno_id', alumnoId);
  addParam(query, 'visto_por_coach', typeof vistoPorCoach === 'boolean' ? vistoPorCoach : undefined);

  const resp = await client.get('/api/analytics/alerts/', { params: query, signal });
  return resp.data;
}

