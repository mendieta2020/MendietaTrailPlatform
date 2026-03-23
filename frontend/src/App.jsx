import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

// 1. Importamos el ADN Visual (Tema Corporativo)
import theme from './theme/theme';

// 2. Importamos las Páginas (Vistas)
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Athletes from './pages/Athletes';
import AthleteDetail from './pages/AthleteDetail'; // <--- NUEVA IMPORTACIÓN (Perfil del Atleta)
import CalendarPage from './pages/Calendar';
import Teams from './pages/Teams';
import TeamDetail from './pages/TeamDetail';
import Alerts from './pages/Alerts';
import Connections from './pages/Connections';
import CoachDashboard from './pages/CoachDashboard';
import WorkoutLibraryPage from './pages/WorkoutLibraryPage';
import Finanzas from './pages/Finanzas';
import { useAuth } from './context/AuthContext';

// 3. Páginas públicas (sin autenticación requerida)
import LandingPage from './pages/public/LandingPage';
import PrivacyPage from './pages/public/PrivacyPage';
import TermsPage from './pages/public/TermsPage';
import SecurityPage from './pages/public/SecurityPage';
import VendorPage from './pages/public/VendorPage';


// --- COMPONENTE DE SEGURIDAD (GUARDIÁN) ---
// Verifica si existe un token válido. Si no, redirige al Login.
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return null;
  }

  if (!user) {
    if (import.meta.env.DEV) {
      console.debug('[Auth] protected route redirect to /login');
    }
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

function App() {
  return (
    <ThemeProvider theme={theme}>
      {/* CssBaseline: Reset CSS estándar para consistencia visual */}
      <CssBaseline />

      <BrowserRouter>
        <Routes>

          {/* ── RUTAS PÚBLICAS (sin autenticación) ───────── */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/vendor" element={<VendorPage />} />
          <Route path="/vendor/:doc" element={<VendorPage />} />

          {/* --- RUTAS PRIVADAS (ÁREA SEGURA) --- */}

          {/* 1. Panel Principal (Torre de Control) */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />

          {/* 2. Mi Organización (Coach Dashboard P1) */}
          <Route
            path="/coach-dashboard"
            element={
              <ProtectedRoute>
                <CoachDashboard />
              </ProtectedRoute>
            }
          />

          {/* 3. Librería de Entrenamientos (P2) */}
          <Route
            path="/library"
            element={
              <ProtectedRoute>
                <WorkoutLibraryPage />
              </ProtectedRoute>
            }
          />

          {/* 4. Calendario de Temporada */}
          <Route
            path="/calendar"
            element={
              <ProtectedRoute>
                <CalendarPage />
              </ProtectedRoute>
            }
          />

          {/* 3. Gestión de Equipos (LISTADO) */}
          <Route
            path="/teams"
            element={
              <ProtectedRoute>
                <Teams />
              </ProtectedRoute>
            }
          />

          {/* 4. Detalle de Equipo (VISTA ESPECÍFICA) */}
          <Route
            path="/teams/:id"
            element={
              <ProtectedRoute>
                <TeamDetail />
              </ProtectedRoute>
            }
          />

          {/* 5. Gestión de Alumnos (LISTADO CRM) */}
          <Route
            path="/athletes"
            element={
              <ProtectedRoute>
                <Athletes />
              </ProtectedRoute>
            }
          />

          {/* 6. Perfil del Atleta (VISTA INDIVIDUAL - NUEVA) */}
          <Route
            path="/athletes/:id"
            element={
              <ProtectedRoute>
                <AthleteDetail />
              </ProtectedRoute>
            }
          />

          {/* 7. Alertas */}
          <Route
            path="/alerts"
            element={
              <ProtectedRoute>
                <Alerts />
              </ProtectedRoute>
            }
          />

          {/* 8. Conexiones con Plataformas */}
          <Route
            path="/connections"
            element={
              <ProtectedRoute>
                <Connections />
              </ProtectedRoute>
            }
          />

          {/* 9. Finanzas — owner/admin billing dashboard */}
          <Route
            path="/finance"
            element={
              <ProtectedRoute>
                <Finanzas />
              </ProtectedRoute>
            }
          />

          {/* RUTA COMODÍN: Cualquier dirección desconocida redirige al Login */}
          <Route path="*" element={<Navigate to="/login" replace />} />

        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
