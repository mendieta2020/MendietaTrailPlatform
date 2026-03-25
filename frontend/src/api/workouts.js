import client from './client';

export function getPaceZones() {
  return client.get('/api/athlete/pace-zones/');
}
