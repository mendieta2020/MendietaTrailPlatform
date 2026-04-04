import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar, Badge, Tooltip,
  BottomNavigation, BottomNavigationAction, useTheme, useMediaQuery,
} from '@mui/material';
import {
  Home,
  CalendarMonth,
  BarChart,
  Link as LinkIcon,
  Person,
  Logout,
  Notifications as NotificationsIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { logoutSession } from '../api/authClient';
import { getMessages, markMessageRead } from '../api/messages';
import { useOrg } from '../context/OrgContext';
import MessagesDrawer from './MessagesDrawer';
import PWAInstallPrompt from './PWAInstallPrompt';

const DRAWER_EXPANDED = 260;
const DRAWER_COLLAPSED = 60;
const LS_KEY = 'athlete_sidebar_collapsed';

const menuItems = [
  { text: 'Hoy', icon: <Home />, path: '/dashboard' },
  { text: 'Mi Entrenamiento', icon: <CalendarMonth />, path: '/athlete/training' },
  { text: 'Mi Progreso', icon: <BarChart />, path: '/athlete/progress' },
  { text: 'Conexiones', icon: <LinkIcon />, path: '/connections' },
  { text: 'Perfil', icon: <Person />, path: '/athlete/profile' },
];

// Bottom tabs for athlete (xs only)
const ATHLETE_BOTTOM_TABS = [
  { label: 'Hoy',      icon: <Home sx={{ fontSize: 22 }} />,         value: '/dashboard' },
  { label: 'Entreno',  icon: <CalendarMonth sx={{ fontSize: 22 }} />, value: '/athlete/training' },
  { label: 'Progreso', icon: <BarChart sx={{ fontSize: 22 }} />,      value: '/athlete/progress' },
  { label: 'Perfil',   icon: <Person sx={{ fontSize: 22 }} />,        value: '/athlete/profile' },
];

const AthleteLayout = ({ children, user }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(LS_KEY) === 'true'; } catch { return false; }
  });
  const [openMessages, setOpenMessages] = useState(false);
  const [messages, setMessages] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const pollingRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id ?? null;

  const drawerWidth = collapsed ? DRAWER_COLLAPSED : DRAWER_EXPANDED;

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(LS_KEY, String(next)); } catch { /* storage unavailable */ }
  };

  const fetchMessages = useCallback(() => {
    if (!orgId) return;
    getMessages(orgId)
      .then((res) => {
        setMessages(res.data?.results ?? []);
        setCoaches(res.data?.coaches ?? []);
      })
      .catch(() => {});
  }, [orgId]);

  useEffect(() => {
    fetchMessages();
    pollingRef.current = setInterval(fetchMessages, 60000);
    return () => clearInterval(pollingRef.current);
  }, [fetchMessages]);

  const unreadCount = messages.filter((m) => !m.read_at).length;

  const handleOpenMessages = () => {
    setOpenMessages(true);
    const unread = messages.filter((m) => !m.read_at);
    unread.forEach((m) => {
      markMessageRead(orgId, m.id)
        .then(() => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === m.id ? { ...msg, read_at: new Date().toISOString() } : msg
            )
          );
        })
        .catch(() => {});
    });
  };

  const handleLogout = async () => {
    await logoutSession();
    window.location.href = '/';
  };

  const handleAthleteSessionClick = (referenceId, referenceDate) => {
    sessionStorage.setItem('openAssignmentId', String(referenceId));
    if (referenceDate) sessionStorage.setItem('openAssignmentDate', referenceDate);
    navigate('/athlete/training');
  };

  const initials = user?.first_name && user?.last_name
    ? `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()
    : (user?.username?.[0] ?? '?').toUpperCase();

  const displayName = user?.first_name
    ? `${user.first_name}${user.last_name ? ' ' + user.last_name : ''}`
    : user?.username ?? '';

  const drawer = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#1A2027', color: 'white' }}>
      <Toolbar sx={{ display: 'flex', justifyContent: 'center', py: 2, minHeight: 56 }}>
        {collapsed ? (
          <Typography variant="h6" noWrap sx={{ fontWeight: 'bold', color: '#F57C00', fontSize: '1rem' }}>
            SM
          </Typography>
        ) : (
          <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold', letterSpacing: 1, color: '#F57C00' }}>
            SENDERO <span style={{ color: 'white' }}>MENDIETA</span>
          </Typography>
        )}
      </Toolbar>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      {/* Athlete avatar + name — only when expanded */}
      {!collapsed && (
        <>
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
        </>
      )}

      <List sx={{ flexGrow: 1, px: collapsed ? 0.5 : 1, mt: 1 }}>
        {menuItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <ListItem key={item.text} disablePadding sx={{ mb: 1 }}>
              <Tooltip title={collapsed ? item.text : ''} placement="right" arrow>
                <ListItemButton
                  onClick={() => navigate(item.path)}
                  selected={isActive}
                  sx={{
                    borderRadius: 2,
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    px: collapsed ? 1 : 2,
                    '&.Mui-selected': {
                      bgcolor: 'rgba(245, 124, 0, 0.15)',
                      borderLeft: collapsed ? 'none' : '4px solid #F57C00',
                      color: '#F57C00',
                    },
                    '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                  }}
                >
                  <ListItemIcon sx={{
                    minWidth: collapsed ? 0 : 40,
                    color: isActive ? '#F57C00' : '#94A3B8',
                    justifyContent: 'center',
                  }}>
                    {item.icon}
                  </ListItemIcon>
                  {!collapsed && (
                    <ListItemText
                      primary={item.text}
                      primaryTypographyProps={{
                        fontSize: '0.9rem',
                        fontWeight: isActive ? 600 : 400,
                      }}
                    />
                  )}
                </ListItemButton>
              </Tooltip>
            </ListItem>
          );
        })}
      </List>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      <List sx={{ px: collapsed ? 0.5 : 1 }}>
        <ListItem disablePadding>
          <Tooltip title={collapsed ? 'Cerrar Sesión' : ''} placement="right" arrow>
            <ListItemButton
              onClick={handleLogout}
              sx={{
                borderRadius: 2,
                justifyContent: collapsed ? 'center' : 'flex-start',
                px: collapsed ? 1 : 2,
                '&:hover': { bgcolor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
              }}
            >
              <ListItemIcon sx={{ minWidth: collapsed ? 0 : 40, color: '#64748B', justifyContent: 'center' }}>
                <Logout />
              </ListItemIcon>
              {!collapsed && (
                <ListItemText primary="Cerrar Sesión" primaryTypographyProps={{ fontSize: '0.9rem' }} />
              )}
            </ListItemButton>
          </Tooltip>
        </ListItem>
      </List>

      {/* COLLAPSE TOGGLE */}
      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 0.75 }}>
        <Tooltip title={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'} placement="right" arrow>
          <IconButton
            size="small"
            onClick={toggleCollapsed}
            sx={{ color: '#64748B', '&:hover': { color: '#F57C00' } }}
          >
            {collapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>
    </div>
  );

  // Determine active bottom tab value
  const activeBottomTab = ATHLETE_BOTTOM_TABS.find(
    (t) => location.pathname.startsWith(t.value)
  )?.value ?? false;

  return (
    <Box sx={{ display: 'flex' }}>
      {/* APPBAR */}
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
          bgcolor: 'white',
          color: '#1E293B',
          boxShadow: '0 1px 3px 0 rgba(0,0,0,0.1)',
          transition: 'width 0.2s ease, margin-left 0.2s ease',
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 48, sm: 64 }, px: { xs: 2, sm: 3 } }}>
          {isMobile ? (
            /* Mobile compact header */
            <>
              <Typography
                noWrap
                sx={{ fontWeight: 800, fontSize: '0.9rem', letterSpacing: 1, color: '#F57C00' }}
              >
                S. <span style={{ color: '#1E293B' }}>MENDIETA</span>
              </Typography>
              <Box sx={{ flexGrow: 1 }} />
              <IconButton color="inherit" size="small" onClick={handleOpenMessages} sx={{ mr: 0.5 }}>
                <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
                  <NotificationsIcon fontSize="small" />
                </Badge>
              </IconButton>
              <Avatar
                sx={{ bgcolor: '#F57C00', fontWeight: 'bold', width: 30, height: 30, fontSize: '0.75rem' }}
                onClick={() => navigate('/athlete/profile')}
              >
                {initials}
              </Avatar>
            </>
          ) : (
            /* Desktop header */
            <>
              <IconButton color="inherit" edge="start" onClick={() => setMobileOpen(!mobileOpen)} sx={{ mr: 2, display: { sm: 'none' } }}>
                {/* Not shown — xs only and we use bottom nav */}
              </IconButton>
              <Typography variant="h6" noWrap sx={{ flexGrow: 1, fontWeight: 700, fontSize: '1.1rem' }}>
                Panel del Atleta
              </Typography>
              <IconButton color="inherit" onClick={handleOpenMessages} sx={{ mr: 1 }}>
                <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
                  <NotificationsIcon />
                </Badge>
              </IconButton>
              <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold', width: 32, height: 32, fontSize: '0.8rem' }}>
                {initials}
              </Avatar>
            </>
          )}
        </Toolbar>
      </AppBar>

      {/* PWA install prompt (mobile only) */}
      <PWAInstallPrompt />

      {/* SIDEBAR — hidden on mobile (xs), shown on sm+ */}
      <Box
        component="nav"
        sx={{
          width: { sm: drawerWidth },
          flexShrink: { sm: 0 },
          transition: 'width 0.2s ease',
          display: { xs: 'none', sm: 'block' },
        }}
      >
        <Drawer
          variant="permanent"
          sx={{
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              borderRight: 'none',
              bgcolor: '#1A2027',
              overflowX: 'hidden',
              transition: 'width 0.2s ease',
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* MAIN CONTENT */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2, sm: 3 },
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          bgcolor: '#F1F5F9',
          minHeight: '100vh',
          transition: 'width 0.2s ease',
          pb: { xs: '80px', sm: 3 },
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 48, sm: 64 } }} />
        {children}
      </Box>

      {/* BOTTOM NAVIGATION — xs only */}
      <Box
        sx={{
          display: { xs: 'block', sm: 'none' },
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: 1200,
          borderTop: '1px solid #e2e8f0',
          bgcolor: 'white',
          boxShadow: '0 -2px 8px rgba(0,0,0,0.08)',
        }}
      >
        <BottomNavigation
          value={activeBottomTab}
          onChange={(_, newValue) => {
            if (newValue) navigate(newValue);
          }}
          sx={{
            height: 'auto',
            minHeight: 56,
            paddingBottom: 'env(safe-area-inset-bottom)',
            bgcolor: 'transparent',
            '& .MuiBottomNavigationAction-root': {
              minWidth: 0,
              padding: '6px 4px',
              color: '#94a3b8',
            },
            '& .MuiBottomNavigationAction-root.Mui-selected': {
              color: '#F57C00',
            },
            '& .MuiBottomNavigationAction-label': {
              fontSize: '0.62rem',
              fontWeight: 500,
              marginTop: 2,
            },
            '& .MuiBottomNavigationAction-root.Mui-selected .MuiBottomNavigationAction-label': {
              fontSize: '0.62rem',
              fontWeight: 700,
            },
          }}
        >
          {ATHLETE_BOTTOM_TABS.map((tab) => (
            <BottomNavigationAction
              key={tab.value}
              label={tab.label}
              value={tab.value}
              icon={tab.icon}
              sx={{
                '&.Mui-selected svg': {
                  transform: 'scale(1.05)',
                  transition: 'transform 100ms ease',
                },
              }}
            />
          ))}
        </BottomNavigation>
      </Box>

      <MessagesDrawer
        open={openMessages}
        onClose={() => setOpenMessages(false)}
        messages={messages}
        contacts={coaches}
        orgId={orgId}
        currentUserId={user?.id}
        onMessageSent={fetchMessages}
        onSessionClick={handleAthleteSessionClick}
      />
    </Box>
  );
};

export default AthleteLayout;
