import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

// NOTA DE ARQUITECTURA:
// Hemos eliminado import './index.css' deliberadamente.
// Ahora todo el diseño visual es controlado por Material UI (theme.js),
// lo que garantiza consistencia total en toda la plataforma.

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)