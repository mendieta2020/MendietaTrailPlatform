import client from './client';

export const startStravaOAuth = () => client.post('/api/integrations/strava/start');
