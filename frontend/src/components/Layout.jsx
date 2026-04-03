import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar, Tooltip, Badge, CircularProgress
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
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from '@mui/icons-material';
import { BarChart2 } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { logoutSession } from '../api/authClient';
import { getMessages, markMessageRead } from '../api/messages';
import { listAthletes } from '../api/p1';
import { useOrg } from '../context/OrgContext';
import client from '../api/client';

const DRAWER_EXPANDED = 260;
const DRAWER_COLLAPSED = 60;
const LS_KEY = 'sidebar_collapsed';

const Layout = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(LS_KEY) === 'true'; } catch { return false; }
  });
  const [userRole, setUserRole] = useState(null);
  const [userInfo, setUserInfo] = useState(null);
  const [openMessages, setOpenMessages] = useState(false);
  const [messages, setMessages] = useState([]);
  const [athletes, setAthletes] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
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
      });
  }, []);

  const handleLogout = async () => {
    await logoutSession();
    window.location.href = '/';
  };

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

  useEffect(() => {
    if (!orgId || userRole === 'athlete') return;
    listAthletes(orgId)
      .then((res) => {
        const list = res.data?.results ?? res.data ?? [];
        setAthletes(
          list
            .filter((a) => a.user_id)
            .map((a) => ({
              user_id: a.user_id,
              athlete_id: a.id,
              name: `${a.first_name ?? ''} ${a.last_name ?? ''}`.trim() || a.email || 'Atleta',
            }))
        );
      })
      .catch(() => {});
  }, [orgId, userRole]);

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

  const handleCoachSessionClick = (referenceId, referenceDate, contactUserId) => {
    const athlete = athletes.find((a) => a.user_id === contactUserId);
    if (athlete) {
      sessionStorage.setItem('calendarSelectedTarget', `a:${athlete.athlete_id}`);
    }
    sessionStorage.setItem('calendarOpenAssignment', String(referenceId));
    if (referenceDate) sessionStorage.setItem('calendarOpenAssignmentDate', referenceDate);
    navigate('/calendar');
  };

  const isAdminOrOwner = userRole === 'owner' || userRole === 'admin';

  const menuGroups = [
    {
      label: 'DIARIO',
      items: [
        { text: 'Inicio',      icon: <Dashboard />,            path: '/dashboard' },
        { text: 'Calendario',  icon: <CalendarMonth />,         path: '/calendar' },
        { text: 'Alumnos',     icon: <People />,                path: '/athletes' },
        { text: 'Analytics',   icon: <BarChart2 size={20} />,   path: '/coach/analytics' },
      ],
    },
    {
      label: 'HERRAMIENTAS',
      items: [
        { text: 'Librería',  icon: <LibraryBooksIcon />, path: '/library' },
        { text: 'Plantilla', icon: <GridView />,          path: '/plantilla' },
        { text: 'Grupos',    icon: <Groups />,             path: '/teams' },
      ],
    },
    {
      label: 'CONFIGURACIÓN',
      items: [
        { text: 'Finanzas',         icon: <Payment />,   path: '/finance',        adminOnly: true },
        { text: 'Conexiones',       icon: <LinkIcon />,  path: '/connections' },
        { text: 'Mi Organización',  icon: <Business />,  path: '/coach-dashboard' },
      ],
    },
  ];

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const drawer = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#1A2027', color: 'white' }}>
      {/* HEADER */}
      <Toolbar sx={{ display: 'flex', justifyContent: collapsed ? 'center' : 'center', py: 2, minHeight: 56 }}>
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

      {/* NAV LIST */}
      <List sx={{ flexGrow: 1, px: collapsed ? 0.5 : 1, pt: 1 }}>
        {menuGroups.map((group, gi) => (
          <React.Fragment key={group.label}>
            {gi > 0 && <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', my: 1 }} />}
            {!collapsed && (
              <Typography
                sx={{
                  px: 1.5, pt: gi === 0 ? 0 : 0.5, pb: 0.5,
                  fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.12em',
                  color: 'rgba(148,163,184,0.6)', textTransform: 'uppercase',
                }}
              >
                {group.label}
              </Typography>
            )}
            {group.items.map((item) => {
              const isLocked = item.adminOnly && !isAdminOrOwner;
              const isActive = !isLocked && location.pathname === item.path;
              return (
                <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
                  <Tooltip
                    title={collapsed ? item.text : (isLocked ? 'Solo para administradores de la organización' : '')}
                    placement="right"
                    arrow
                  >
                    <span style={{ width: '100%' }}>
                      <ListItemButton
                        onClick={() => !isLocked && navigate(item.path)}
                        selected={isActive}
                        disabled={isLocked}
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
                          '&.Mui-disabled': { opacity: 0.4 },
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
                            primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: isActive ? 600 : 400 }}
                          />
                        )}
                      </ListItemButton>
                    </span>
                  </Tooltip>
                </ListItem>
              );
            })}
          </React.Fragment>
        ))}
      </List>

      <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)' }} />

      {/* LOGOUT */}
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

      {/* COLLAPSE TOGGLE BUTTON */}
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

  if (userRole === null) {
    return (
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
        <Box sx={{
          width: { sm: DRAWER_EXPANDED },
          flexShrink: { sm: 0 },
          bgcolor: '#1A2027',
          display: { xs: 'none', sm: 'block' },
        }} />
        <Box sx={{
          flexGrow: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          bgcolor: '#F1F5F9',
          minHeight: '100vh',
        }}>
          <CircularProgress />
        </Box>
      </Box>
    );
  }

  if (userRole?.toLowerCase() === 'athlete') {
    return <AthleteLayout user={userInfo}>{children}</AthleteLayout>;
  }

  return (
    <Box sx={{ display: 'flex' }}>
      {/* APPBAR */}
      <AppBar position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
          bgcolor: 'white',
          color: '#1E293B',
          boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
          borderBottom: 'none',
          transition: 'width 0.2s ease, margin-left 0.2s ease',
        }}
      >
        <Toolbar>
          <IconButton color="inherit" edge="start" onClick={handleDrawerToggle} sx={{ mr: 2, display: { sm: 'none' } }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1, fontWeight: 700, fontSize: '1.1rem' }}>
            {userRole === 'athlete' ? 'Panel del Atleta' : 'Panel de Entrenadores'}
          </Typography>
          <IconButton color="inherit" onClick={handleOpenCoachMessages} sx={{ mr: 1 }}>
            <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
              <NotificationsIcon />
            </Badge>
          </IconButton>
          <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold' }}>
            {userInfo?.first_name?.[0] ?? 'C'}{userInfo?.last_name?.[0] ?? ''}
          </Avatar>
        </Toolbar>
      </AppBar>

      {/* MESSAGES DRAWER */}
      <MessagesDrawer
        open={openMessages}
        onClose={() => setOpenMessages(false)}
        messages={messages}
        contacts={athletes}
        orgId={orgId}
        currentUserId={userInfo?.id}
        onMessageSent={fetchCoachMessages}
        onSessionClick={handleCoachSessionClick}
      />

      {/* SIDEBAR */}
      <Box
        component="nav"
        sx={{
          width: { sm: drawerWidth },
          flexShrink: { sm: 0 },
          transition: 'width 0.2s ease',
        }}
      >
        {/* Mobile */}
        <Drawer variant="temporary" open={mobileOpen} onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_EXPANDED, bgcolor: '#1A2027' },
          }}
        >
          {drawer}
        </Drawer>
        {/* Desktop */}
        <Drawer variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
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
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          bgcolor: '#F1F5F9',
          minHeight: '100vh',
          transition: 'width 0.2s ease',
        }}
      >
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
};

export default Layout;
