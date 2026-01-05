import React, { useState } from 'react';
import { 
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton, 
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar 
} from '@mui/material';
import { 
  Menu as MenuIcon, 
  Dashboard,      // Icono para Inicio
  People,         // Icono para Alumnos
  CalendarMonth,  // Icono para Calendario
  Payment,        // Icono para Finanzas
  Groups,         // <--- NUEVO ICONO PARA GRUPOS
  Logout,         // Icono para Cerrar Sesión
  Settings        // Icono para Configuración (Futuro)
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';

const drawerWidth = 260;

const Layout = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // DEFINICIÓN DEL MENÚ LATERAL
  // Aquí agregamos la nueva opción "Grupos"
  const menuItems = [
    { text: 'Inicio', icon: <Dashboard />, path: '/dashboard' },
    { text: 'Calendario', icon: <CalendarMonth />, path: '/calendar' },
    { text: 'Grupos', icon: <Groups />, path: '/teams' }, // <--- NUEVA OPCIÓN
    { text: 'Alumnos', icon: <People />, path: '/athletes' },
    { text: 'Finanzas', icon: <Payment />, path: '/finance' },
  ];

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const drawer = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#1A2027', color: 'white' }}>
      {/* HEADER DEL MENÚ LATERAL */}
      <Toolbar sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
        {/* En el futuro aquí pondremos el logo .img */}
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold', letterSpacing: 1, color: '#F57C00' }}>
          SENDERO <span style={{ color: 'white' }}>MENDIETA</span>
        </Typography>
      </Toolbar>
      
      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />
      
      {/* LISTA DE NAVEGACIÓN */}
      <List sx={{ flexGrow: 1, px: 1 }}>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
            <ListItemButton 
              onClick={() => navigate(item.path)}
              selected={location.pathname === item.path}
              sx={{
                borderRadius: 2, // Bordes redondeados en los botones del menú (Moderno)
                '&.Mui-selected': { 
                  bgcolor: 'rgba(245, 124, 0, 0.15)', 
                  borderLeft: '4px solid #F57C00', // Indicador visual a la izquierda
                  color: '#F57C00'
                },
                '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' }
              }}
            >
              <ListItemIcon sx={{ minWidth: 40, color: location.pathname === item.path ? '#F57C00' : '#94A3B8' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText 
                primary={item.text} 
                primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: location.pathname === item.path ? 600 : 400 }} 
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      
      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />
      
      {/* FOOTER DEL MENÚ (CERRAR SESIÓN) */}
      <List sx={{ px: 1 }}>
        <ListItem disablePadding>
          <ListItemButton 
            onClick={() => {
              try { localStorage.clear(); } catch (e) { /* ignore */ }
              window.location.href = '/';
            }}
            sx={{ borderRadius: 2, '&:hover': { bgcolor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' } }}
          >
            <ListItemIcon sx={{ minWidth: 40, color: '#64748B' }}><Logout /></ListItemIcon>
            <ListItemText primary="Cerrar Sesión" primaryTypographyProps={{ fontSize: '0.9rem' }} />
          </ListItemButton>
        </ListItem>
      </List>
    </div>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      {/* BARRA SUPERIOR (HEADER) */}
      <AppBar position="fixed" 
        sx={{ 
          width: { sm: `calc(100% - ${drawerWidth}px)` }, 
          ml: { sm: `${drawerWidth}px` },
          bgcolor: 'white', 
          color: '#1E293B', 
          boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)', // Sombra sutil profesional
          borderBottom: 'none'
        }}
      >
        <Toolbar>
          <IconButton color="inherit" edge="start" onClick={handleDrawerToggle} sx={{ mr: 2, display: { sm: 'none' } }}>
            <MenuIcon />
          </IconButton>
          
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1, fontWeight: 700, fontSize: '1.1rem' }}>
            Panel de Entrenadores 🚀
          </Typography>
          
          {/* Avatar del usuario (Esquina superior derecha) */}
          <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold' }}>FM</Avatar>
        </Toolbar>
      </AppBar>

      {/* MENÚ LATERAL (DRAWER) */}
      <Box component="nav" sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}>
        {/* Móvil */}
        <Drawer variant="temporary" open={mobileOpen} onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{ display: { xs: 'block', sm: 'none' }, '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth, bgcolor: '#1A2027' } }}
        >
          {drawer}
        </Drawer>
        {/* Desktop */}
        <Drawer variant="permanent"
          sx={{ display: { xs: 'none', sm: 'block' }, '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth, borderRight: 'none', bgcolor: '#1A2027' } }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* CONTENIDO PRINCIPAL */}
      <Box component="main" sx={{ flexGrow: 1, p: 3, width: { sm: `calc(100% - ${drawerWidth}px)` }, bgcolor: '#F1F5F9', minHeight: '100vh' }}>
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
};

export default Layout;