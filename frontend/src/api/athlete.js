import client from './client';

export function getDeviceStatus() {
  return client.get('/api/athlete/device-status/');
}

export function dismissDevicePreference(reason = 'no_device') {
  return client.post('/api/athlete/device-preference/dismiss/', { reason });
}

export function reactivateDevicePreference() {
  return client.post('/api/athlete/device-preference/reactivate/');
}

export function getNotifications() {
  return client.get('/api/athlete/notifications/');
}

export function markNotificationRead(id) {
  return client.post(`/api/athlete/notifications/${id}/mark-read/`);
}
