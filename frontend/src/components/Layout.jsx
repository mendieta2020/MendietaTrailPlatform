import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar, Tooltip, Badge
} from '@mui/material';
import AthleteLayout from './AthleteLayout';
import MessagesDrawer from './MessagesDrawer';
import {
  Menu as MenuIcon,
  Dashboard,
  People,
  CalendarMonth,
  Payment,
  Groups,
  GridView,
  Link as LinkIcon,
  Logout,
  Settings,
  Business,
  LibraryBooks as LibraryBooksIcon,
  Notifications as NotificationsIcon,
} from '@mui/icons-material';
import { BarChart2 } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { logoutSession } from '../api/authClient';
import { getMessages, markMessageRead } from '../api/messages';
import { useOrg } from '../context/OrgContext';
import client from '../api/client';

const drawerWidth = 260;

const Layout = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userRole, setUserRole] = useState('coach'); // Default to coach
  const [userInfo, setUserInfo] = useState(null);
  const [openMessages, setOpenMessages] = useState(false);
  const [messages, setMessages] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const pollingRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id ?? null;

  // Fetch user role on mount
  useEffect(() => {
    client.get('/api/me')
      .then(res => {
        setUserRole(res.data.role);
        setUserInfo(res.data);
      })
      .catch(err => {
        if (import.meta.env.DEV) {
          console.error('Failed to fetch user role:', err);
        }
        // Silently default to 'coach' on error
      });
  }, []);

  const handleLogout = async () => {
    await logoutSession();
    window.location.href = '/';
  };

  // ── Coach notification bell ────────────────────────────────────────────────
  const fetchCoachMessages = useCallback(() => {
    if (!orgId || userRole === 'athlete') return;
    getMessages(orgId)
      .then((res) => {
        setMessages(res.data?.results ?? []);
        setUnreadCount(res.data?.unread_count ?? 0);
      })
      .catch(() => {});
  }, [orgId, userRole]);

  useEffect(() => {
    fetchCoachMessages();
    pollingRef.current = setInterval(fetchCoachMessages, 60000);
    return () => clearInterval(pollingRef.current);
  }, [fetchCoachMessages]);

  const handleOpenCoachMessages = () => {
    setOpenMessages(true);
    const unread = messages.filter((m) => !m.read_at && m.sender_id !== userInfo?.id);
    unread.forEach((m) => {
      markMessageRead(orgId, m.id)
        .then(() => {
          setMessages((prev) =>
            prev.map((msg) => msg.id === m.id ? { ...msg, read_at: new Date().toISOString() } : msg)
          );
          setUnreadCount((c) => Math.max(0, c - 1));
        })
        .catch(() => {});
    });
  };

  const isAdminOrOwner = userRole === 'owner' || userRole === 'admin';

  // DEFINICIÓN DEL MENÚ LATERAL
  const menuItems = [
    { text: 'Inicio', icon: <Dashboard />, path: '/dashboard' },
    { text: 'Mi Organización', icon: <Business />, path: '/coach-dashboard' },
    { text: 'Librería', icon: <LibraryBooksIcon />, path: '/library' },
    { text: 'Calendario', icon: <CalendarMonth />, path: '/calendar' },
    { text: 'Plantilla', icon: <GridView />, path: '/plantilla' },
    { text: 'Grupos', icon: <Groups />, path: '/teams' },
    { text: 'Alumnos', icon: <People />, path: '/athletes' },
    { text: 'Analytics', icon: <BarChart2 size={20} />, path: '/coach/analytics' },
    { text: 'Finanzas', icon: <Payment />, path: '/finance', adminOnly: true },
    { text: 'Conexiones', icon: <LinkIcon />, path: '/connections' }, // <--- NUEVA OPCIÓN
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
        {menuItems.map((item) => {
          const isLocked = item.adminOnly && !isAdminOrOwner;
          return (
            <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
              <Tooltip
                title={isLocked ? 'Solo para administradores de la organización' : ''}
                placement="right"
                arrow
              >
                <span style={{ width: '100%' }}>
                  <ListItemButton
                    onClick={() => !isLocked && navigate(item.path)}
                    selected={!isLocked && location.pathname === item.path}
                    disabled={isLocked}
                    sx={{
                      borderRadius: 2,
                      '&.Mui-selected': {
                        bgcolor: 'rgba(245, 124, 0, 0.15)',
                        borderLeft: '4px solid #F57C00',
                        color: '#F57C00'
                      },
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                      '&.Mui-disabled': { opacity: 0.4 },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 40, color: (!isLocked && location.pathname === item.path) ? '#F57C00' : '#94A3B8' }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.text}
                      primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: (!isLocked && location.pathname === item.path) ? 600 : 400 }}
                    />
                  </ListItemButton>
                </span>
              </Tooltip>
            </ListItem>
          );
        })}
      </List>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      {/* FOOTER DEL MENÚ (CERRAR SESIÓN) */}
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

  // Delegate to athlete layout ONLY for role=athlete (case-insensitive safety)
  if (userRole?.toLowerCase() === 'athlete') {
    return <AthleteLayout user={userInfo}>{children}</AthleteLayout>;
  }

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
            {userRole === 'athlete' ? 'Panel del Atleta 🚀' : 'Panel de Entrenadores 🚀'}
          </Typography>

          {/* 🔔 Coach notification bell */}
          <IconButton color="inherit" onClick={handleOpenCoachMessages} sx={{ mr: 1 }}>
            <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
              <NotificationsIcon />
            </Badge>
          </IconButton>

          {/* Avatar del usuario (Esquina superior derecha) */}
          <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold' }}>
            {userInfo?.first_name?.[0] ?? 'C'}{userInfo?.last_name?.[0] ?? ''}
          </Avatar>
        </Toolbar>
      </AppBar>

      {/* Coach messages drawer */}
      <MessagesDrawer
        open={openMessages}
        onClose={() => setOpenMessages(false)}
        messages={messages}
        coaches={[]}
        orgId={orgId}
        currentUserId={userInfo?.id}
        onMessageSent={fetchCoachMessages}
      />

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
