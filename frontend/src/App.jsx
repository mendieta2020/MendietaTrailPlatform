import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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

// --- COMPONENTE DE SEGURIDAD (GUARDIÁN) ---
// Verifica si existe un token válido. Si no, redirige al Login.
const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('access_token');
  
  if (!token) {
    return <Navigate to="/" replace />;
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
          
          {/* RUTA PÚBLICA: Login */}
          <Route path="/" element={<Login />} />

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

          {/* 2. Calendario de Temporada */}
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

          {/* 7. Finanzas (Placeholder para el futuro inmediato) */}
          <Route 
            path="/finance" 
            element={
              <ProtectedRoute>
                {/* Por ahora redirige al dashboard, pronto tendrá su propia pantalla */}
                <Navigate to="/dashboard" replace />
              </ProtectedRoute>
            } 
          />

          {/* RUTA COMODÍN: Cualquier dirección desconocida redirige al Login */}
          <Route path="*" element={<Navigate to="/" replace />} />

        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;