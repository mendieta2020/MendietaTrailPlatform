import React from 'react';

import { startStravaOAuth } from '../api/integrations';

const AthleteIntegrations = () => {
  const handleConnect = async () => {
    try {
      const response = await startStravaOAuth();
      const oauthUrl = response?.data?.oauth_url;
      if (!oauthUrl) {
        console.error('[Strava] Missing oauth_url in response', response?.data);
        alert('No se pudo iniciar la conexión con Strava.');
        return;
      }
      window.location.href = oauthUrl;
    } catch (error) {
      console.error('[Strava] OAuth start failed', error);
      alert('No se pudo iniciar la conexión con Strava.');
    }
  };

  return (
    <div>
      <h1>Integraciones</h1>
      <button type="button" onClick={handleConnect}>
        Conectar Strava
      </button>
    </div>
  );
};

export default AthleteIntegrations;
