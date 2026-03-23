import client from './client';

export function notifyAthleteDevice(membershipId) {
  return client.post(`/api/coach/roster/${membershipId}/notify-device/`);
}
