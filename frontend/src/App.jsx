import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { GoogleOAuthProvider } from '@react-oauth/google';

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
import { useOrg } from './context/OrgContext';

// 3. Páginas públicas (sin autenticación requerida)
import LandingPage from './pages/public/LandingPage';
import PrivacyPage from './pages/public/PrivacyPage';
import TermsPage from './pages/public/TermsPage';
import SecurityPage from './pages/public/SecurityPage';
import VendorPage from './pages/public/VendorPage';
import InvitePage from './pages/InvitePage';
import JoinPage from './pages/JoinPage';
import AthleteDashboard from './pages/AthleteDashboard';
import AthleteMyTraining from './pages/AthleteMyTraining';
import AthleteProgress from './pages/AthleteProgress';
import AthleteProfile from './pages/AthleteProfile';
import CoachAnalytics from './pages/CoachAnalytics';
import CoachAthletePMC from './pages/CoachAthletePMC';
import Plantilla from './pages/Plantilla';


// --- ATHLETE DETAIL REDIRECT: /athletes/:id → /coach/athletes/:id/pmc ---
const AthleteDetailRedirect = () => {
  const { id } = useParams();
  return <Navigate to={`/coach/athletes/${id}/pmc`} replace />;
};

// --- DASHBOARD ROUTER: renders athlete or coach dashboard based on active org role ---
const DashboardRouter = () => {
  const { user, loading } = useAuth();
  const { activeOrg, orgLoading } = useOrg();
  if (loading || orgLoading) return null;
  if (activeOrg?.role === 'athlete') {
    return <AthleteDashboard user={user} />;
  }
  return <Dashboard />;
};

// --- COACH ROUTE: blocks athletes from coach-only pages ---
const CoachRoute = ({ children }) => {
  const { loading } = useAuth();
  const { activeOrg, orgLoading } = useOrg();
  if (loading || orgLoading) return null;
  if (activeOrg?.role === 'athlete') {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
};

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
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

  return (
    <GoogleOAuthProvider clientId={googleClientId}>
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
          <Route path="/invite/:token" element={<InvitePage />} />
          <Route path="/join/:slug" element={<JoinPage />} />

          {/* --- RUTAS PRIVADAS (ÁREA SEGURA) --- */}

          {/* 1. Panel Principal — role-aware: athletes → AthleteDashboard, others → Dashboard */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardRouter />
              </ProtectedRoute>
            }
          />

          {/* Athlete-specific pages */}
          <Route
            path="/athlete/training"
            element={
              <ProtectedRoute>
                <AthleteMyTraining />
              </ProtectedRoute>
            }
          />
          <Route
            path="/athlete/progress"
            element={
              <ProtectedRoute>
                <AthleteProgress />
              </ProtectedRoute>
            }
          />
          <Route
            path="/athlete/profile"
            element={
              <ProtectedRoute>
                <AthleteProfile />
              </ProtectedRoute>
            }
          />

          {/* 2. Mi Organización (Coach Dashboard P1) */}
          <Route
            path="/coach-dashboard"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <CoachDashboard />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 3. Librería de Entrenamientos (P2) */}
          <Route
            path="/library"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <WorkoutLibraryPage />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 4. Calendario de Temporada */}
          <Route
            path="/calendar"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <CalendarPage />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 4b. Plantilla de Entrenamiento (PR-145h) */}
          <Route
            path="/plantilla"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <Plantilla />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 3. Gestión de Equipos (LISTADO) */}
          <Route
            path="/teams"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <Teams />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 4. Detalle de Equipo (VISTA ESPECÍFICA) */}
          <Route
            path="/teams/:id"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <TeamDetail />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 5. Gestión de Alumnos (LISTADO CRM) */}
          <Route
            path="/athletes"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <Athletes />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* 6. Perfil del Atleta (VISTA INDIVIDUAL) → redirect to new PMC view */}
          <Route
            path="/athletes/:id"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <AthleteDetailRedirect />
                </CoachRoute>
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

          {/* 10. Coach Analytics (PMC team view) */}
          <Route
            path="/coach/analytics"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <CoachAnalytics />
                </CoachRoute>
              </ProtectedRoute>
            }
          />
          <Route
            path="/coach/athletes/:membershipId/pmc"
            element={
              <ProtectedRoute>
                <CoachRoute>
                  <CoachAthletePMC />
                </CoachRoute>
              </ProtectedRoute>
            }
          />

          {/* RUTA COMODÍN: Cualquier dirección desconocida redirige al Login */}
          <Route path="*" element={<Navigate to="/login" replace />} />

        </Routes>
      </BrowserRouter>
    </ThemeProvider>
    </GoogleOAuthProvider>
  );
}

export default App;
