import React, { useState } from 'react';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar
} from '@mui/material';
import {
  Menu as MenuIcon,
  Home,
  CalendarMonth,
  BarChart,
  Link as LinkIcon,
  Person,
  Logout,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { logoutSession } from '../api/authClient';

const drawerWidth = 260;

const menuItems = [
  { text: 'Hoy', icon: <Home />, path: '/dashboard' },
  { text: 'Mi Entrenamiento', icon: <CalendarMonth />, path: '/athlete/training' },
  { text: 'Mi Progreso', icon: <BarChart />, path: '/athlete/progress' },
  { text: 'Conexiones', icon: <LinkIcon />, path: '/connections' },
  { text: 'Perfil', icon: <Person />, path: '/athlete/profile' },
];

const AthleteLayout = ({ children, user }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logoutSession();
    window.location.href = '/';
  };

  const initials = user?.first_name && user?.last_name
    ? `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()
    : (user?.username?.[0] ?? '?').toUpperCase();

  const displayName = user?.first_name
    ? `${user.first_name}${user.last_name ? ' ' + user.last_name : ''}`
    : user?.username ?? '';

  const drawer = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#1A2027', color: 'white' }}>
      <Toolbar sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold', letterSpacing: 1, color: '#F57C00' }}>
          SENDERO <span style={{ color: 'white' }}>MENDIETA</span>
        </Typography>
      </Toolbar>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      {/* Athlete avatar + name */}
      <Box sx={{ px: 2, py: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold', width: 36, height: 36, fontSize: '0.85rem' }}>
          {initials}
        </Avatar>
        <Box>
          <Typography variant="body2" sx={{ color: 'white', fontWeight: 600, lineHeight: 1.2 }}>
            {displayName}
          </Typography>
          <Typography variant="caption" sx={{ color: '#64748B' }}>Atleta</Typography>
        </Box>
      </Box>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      <List sx={{ flexGrow: 1, px: 1, mt: 1 }}>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
            <ListItemButton
              onClick={() => navigate(item.path)}
              selected={location.pathname === item.path}
              sx={{
                borderRadius: 2,
                '&.Mui-selected': {
                  bgcolor: 'rgba(245, 124, 0, 0.15)',
                  borderLeft: '4px solid #F57C00',
                  color: '#F57C00',
                },
                '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 40, color: location.pathname === item.path ? '#F57C00' : '#94A3B8' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.text}
                primaryTypographyProps={{
                  fontSize: '0.9rem',
                  fontWeight: location.pathname === item.path ? 600 : 400,
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      <List sx={{ px: 1 }}>
        <ListItem disablePadding>
          <ListItemButton
            onClick={handleLogout}
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
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
          bgcolor: 'white',
          color: '#1E293B',
          boxShadow: '0 1px 3px 0 rgba(0,0,0,0.1)',
        }}
      >
        <Toolbar>
          <IconButton color="inherit" edge="start" onClick={() => setMobileOpen(!mobileOpen)} sx={{ mr: 2, display: { sm: 'none' } }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap sx={{ flexGrow: 1, fontWeight: 700, fontSize: '1.1rem' }}>
            Panel del Atleta
          </Typography>
          <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold', width: 32, height: 32, fontSize: '0.8rem' }}>
            {initials}
          </Avatar>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ display: { xs: 'block', sm: 'none' }, '& .MuiDrawer-paper': { width: drawerWidth, bgcolor: '#1A2027' } }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{ display: { xs: 'none', sm: 'block' }, '& .MuiDrawer-paper': { width: drawerWidth, borderRight: 'none', bgcolor: '#1A2027' } }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, p: 3, width: { sm: `calc(100% - ${drawerWidth}px)` }, bgcolor: '#F1F5F9', minHeight: '100vh' }}>
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
};

export default AthleteLayout;
