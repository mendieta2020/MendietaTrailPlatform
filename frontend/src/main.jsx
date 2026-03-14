import * as Sentry from "@sentry/react";
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { OrgProvider } from './context/OrgContext.jsx'

// Sentry: initialize only when VITE_SENTRY_DSN is present.
// No Session Replay, no Profiling — P0 minimal footprint.
// Set VITE_SENTRY_DSN in Vercel environment variables; never commit a real DSN.
const _sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (_sentryDsn) {
  Sentry.init({
    dsn: _sentryDsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT,
    release: import.meta.env.VITE_SENTRY_RELEASE,
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
}

// NOTA DE ARQUITECTURA:
// Hemos eliminado import './index.css' deliberadamente.
// Ahora todo el diseño visual es controlado por Material UI (theme.js),
// lo que garantiza consistencia total en toda la plataforma.

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <OrgProvider>
        <App />
      </OrgProvider>
    </AuthProvider>
  </StrictMode>,
)
