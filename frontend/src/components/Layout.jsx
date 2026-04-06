import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Drawer, AppBar, Toolbar, List, Typography, Divider, IconButton,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Avatar, Tooltip, Badge,
  CircularProgress, BottomNavigation, BottomNavigationAction, SwipeableDrawer,
  useTheme, useMediaQuery,
} from '@mui/material';
import AthleteLayout from './AthleteLayout';
import MessagesDrawer from './MessagesDrawer';
import PWAInstallPrompt from './PWAInstallPrompt';
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
  Business,
  LibraryBooks as LibraryBooksIcon,
  Notifications as NotificationsIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
  MoreHoriz,
  Person,
} from '@mui/icons-material';
import { BarChart2 } from 'lucide-react';
import QuantorynLogo from './QuantorynLogo';
import { useNavigate, useLocation } from 'react-router-dom';
import { logoutSession } from '../api/authClient';
import { getMessages, markMessageRead } from '../api/messages';
import { listAthletes } from '../api/p1';
import { useOrg } from '../context/OrgContext';
import client from '../api/client';

const DRAWER_EXPANDED = 260;
const DRAWER_COLLAPSED = 60;
const LS_KEY = 'sidebar_collapsed';

// Bottom tabs for coach (xs only)
const COACH_BOTTOM_TABS = [
  { label: 'Inicio',     icon: <Dashboard sx={{ fontSize: 22 }} />,        value: '/dashboard' },
  { label: 'Calendario', icon: <CalendarMonth sx={{ fontSize: 22 }} />,    value: '/calendar' },
  { label: 'Atletas',    icon: <People sx={{ fontSize: 22 }} />,            value: '/athletes' },
  { label: 'Analytics',  icon: <BarChart2 size={22} />,                     value: '/coach/analytics' },
  { label: 'Más',        icon: <MoreHoriz sx={{ fontSize: 22 }} />,         value: 'mas' },
];

const Layout = ({ children }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const [mobileOpen, setMobileOpen] = useState(false); // eslint-disable-line no-unused-vars
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
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
  const isStaff = userRole === 'staff';
  const isCoach = userRole === 'coach';

  // Role-aware sidebar groups
  const menuGroups = isStaff
    ? [
        {
          label: 'GESTIÓN',
          items: [
            { text: 'Alumnos', icon: <People />,  path: '/athletes' },
            { text: 'Grupos',  icon: <Groups />,  path: '/teams' },
            { text: 'Mi Perfil', icon: <Person />, path: '/staff/profile' },
          ],
        },
      ]
    : [
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
            ...(!isCoach ? [{ text: 'Finanzas', icon: <Payment />, path: '/finance', adminOnly: true }] : []),
            { text: 'Conexiones',      icon: <LinkIcon />,  path: '/connections' },
            ...(!isCoach ? [{ text: 'Mi Organización', icon: <Business />, path: '/coach-dashboard' }] : []),
            ...(isCoach ? [{ text: 'Mi Perfil', icon: <Person />, path: '/coach/profile' }] : []),
          ],
        },
      ];

  // "Más" drawer items — role-aware
  const moreItems = isStaff
    ? [
        { text: 'Alumnos',  icon: <People />,  path: '/athletes' },
        { text: 'Grupos',   icon: <Groups />,  path: '/teams' },
        { text: 'Mi Perfil', icon: <Person />, path: '/staff/profile' },
      ]
    : [
        { text: 'Librería',   icon: <LibraryBooksIcon />, path: '/library' },
        { text: 'Plantilla',  icon: <GridView />,          path: '/plantilla' },
        { text: 'Grupos',     icon: <Groups />,             path: '/teams' },
        ...(!isCoach ? [{ text: 'Finanzas', icon: <Payment />, path: '/finance', adminOnly: true }] : []),
        { text: 'Conexiones', icon: <LinkIcon />,           path: '/connections' },
        ...(!isCoach ? [{ text: 'Mi Organización', icon: <Business />, path: '/coach-dashboard' }] : []),
        ...(isCoach ? [{ text: 'Mi Perfil', icon: <Person />, path: '/coach/profile' }] : []),
      ];

  // Role-aware mobile bottom tabs
  const bottomTabs = isStaff
    ? [
        { label: 'Alumnos', icon: <People sx={{ fontSize: 22 }} />,   value: '/athletes' },
        { label: 'Grupos',  icon: <Groups sx={{ fontSize: 22 }} />,   value: '/teams' },
        { label: 'Más',     icon: <MoreHoriz sx={{ fontSize: 22 }} />, value: 'mas' },
      ]
    : COACH_BOTTOM_TABS;

  const drawer = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#0D1117', color: 'white' }}>
      {/* HEADER */}
      <Toolbar sx={{ display: 'flex', justifyContent: 'center', py: 2, minHeight: 56 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: collapsed ? 0 : 1 }}>
          <QuantorynLogo size={collapsed ? 28 : 32} />
          {!collapsed && (
            <Typography noWrap sx={{ fontWeight: 800, fontSize: '0.95rem', letterSpacing: '0.08em', color: '#fff' }}>
              QUANTORYN
            </Typography>
          )}
        </Box>
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
                            bgcolor: 'rgba(0, 212, 170, 0.15)',
                            borderLeft: collapsed ? 'none' : '4px solid #00D4AA',
                            color: '#00D4AA',
                          },
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                          '&.Mui-disabled': { opacity: 0.4 },
                        }}
                      >
                        <ListItemIcon sx={{
                          minWidth: collapsed ? 0 : 40,
                          color: isActive ? '#00D4AA' : '#94A3B8',
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
            sx={{ color: '#64748B', '&:hover': { color: '#00D4AA' } }}
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
          bgcolor: '#0D1117',
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

  // Determine active bottom tab value
  const activeBottomTab = bottomTabs.find(
    (t) => t.value !== 'mas' && location.pathname.startsWith(t.value)
  )?.value ?? false;

  const bottomNavSx = {
    height: 'auto',
    minHeight: 64,
    bgcolor: 'transparent',
    '& .MuiBottomNavigationAction-root': {
      minWidth: 0,
      padding: '6px 4px',
      color: '#8B949E',
    },
    '& .MuiBottomNavigationAction-root.Mui-selected': {
      color: '#00D4AA',
    },
    '& .MuiBottomNavigationAction-label': {
      opacity: '1 !important',
      fontSize: '0.65rem',
      fontWeight: 600,
      marginTop: 2,
    },
    '& .MuiBottomNavigationAction-root.Mui-selected .MuiBottomNavigationAction-label': {
      opacity: '1 !important',
      fontSize: '0.65rem',
      fontWeight: 700,
    },
  };

  // ── MOBILE: flex-column layout — header + scroll area + bottom nav ──
  if (isMobile) {
    return (
      <Box sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100dvh',
        overflow: 'hidden',
      }}>
        {/* HEADER — static, never scrolls */}
        <AppBar position="static" elevation={0} sx={{
          bgcolor: 'white',
          color: '#1E293B',
          borderBottom: '1px solid #e2e8f0',
          flexShrink: 0,
        }}>
          <Toolbar sx={{ minHeight: 48, px: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <QuantorynLogo size={24} color="#00D4AA" />
              <Typography noWrap sx={{ fontWeight: 800, fontSize: '0.85rem', letterSpacing: '0.08em', color: '#0D1117' }}>
                QUANTORYN
              </Typography>
            </Box>
            <Box sx={{ flexGrow: 1 }} />
            <IconButton color="inherit" size="small" onClick={handleOpenCoachMessages} sx={{ mr: 0.5 }}>
              <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
                <NotificationsIcon fontSize="small" />
              </Badge>
            </IconButton>
            <Avatar sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 'bold', width: 30, height: 30, fontSize: '0.75rem' }}>
              {(userInfo?.first_name?.[0] ?? userInfo?.username?.[0] ?? '?').toUpperCase()}{userInfo?.last_name?.[0]?.toUpperCase() ?? ''}
            </Avatar>
          </Toolbar>
        </AppBar>

        {/* SCROLLABLE CONTENT — this is the only thing that scrolls */}
        <Box sx={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          WebkitOverflowScrolling: 'touch',
          bgcolor: '#F1F5F9',
        }}>
          {children}
        </Box>

        {/* BOTTOM NAV — static, never scrolls */}
        <Box sx={{
          flexShrink: 0,
          borderTop: '1px solid #e2e8f0',
          bgcolor: '#FFFFFF',
          boxShadow: '0 -2px 8px rgba(0,0,0,0.08)',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}>
          <BottomNavigation
            value={activeBottomTab}
            onChange={(_, newValue) => {
              if (newValue === 'mas') {
                setMoreDrawerOpen(true);
              } else if (newValue) {
                navigate(newValue);
              }
            }}
            sx={bottomNavSx}
          >
            {bottomTabs.map((tab) => (
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

        {/* "MÁS" BOTTOM SHEET */}
        <SwipeableDrawer
          anchor="bottom"
          open={moreDrawerOpen}
          onOpen={() => setMoreDrawerOpen(true)}
          onClose={() => setMoreDrawerOpen(false)}
          disableSwipeToOpen
          sx={{
            '& .MuiDrawer-paper': {
              borderRadius: '16px 16px 0 0',
              bgcolor: '#0D1117',
              pb: 'env(safe-area-inset-bottom)',
              maxHeight: '80vh',
            },
          }}
        >
          {/* Handle bar */}
          <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1.5, pb: 1 }}>
            <Box sx={{ width: 32, height: 4, bgcolor: 'rgba(255,255,255,0.2)', borderRadius: 2 }} />
          </Box>

          <Typography sx={{ px: 2.5, pb: 1.5, fontSize: '0.65rem', fontWeight: 700, color: 'rgba(148,163,184,0.6)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
            Más opciones
          </Typography>

          <List sx={{ px: 1, pb: 1 }}>
            {moreItems.map((item) => {
              const isLocked = item.adminOnly && !isAdminOrOwner;
              const isActive = !isLocked && location.pathname === item.path;
              return (
                <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
                  <ListItemButton
                    onClick={() => {
                      if (!isLocked) {
                        navigate(item.path);
                        setMoreDrawerOpen(false);
                      }
                    }}
                    disabled={isLocked}
                    sx={{
                      borderRadius: 2,
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' },
                      '&.Mui-disabled': { opacity: 0.4 },
                      bgcolor: isActive ? 'rgba(0, 212, 170,0.15)' : 'transparent',
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 40, color: isActive ? '#00D4AA' : '#94A3B8' }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.text}
                      primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: isActive ? 600 : 400, color: isActive ? '#00D4AA' : 'white' }}
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}

            <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)', my: 1 }} />

            <ListItem disablePadding>
              <ListItemButton
                onClick={() => { setMoreDrawerOpen(false); handleLogout(); }}
                sx={{ borderRadius: 2, '&:hover': { bgcolor: 'rgba(239,68,68,0.1)', color: '#ef4444' } }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: '#64748B' }}>
                  <Logout />
                </ListItemIcon>
                <ListItemText primary="Cerrar Sesión" primaryTypographyProps={{ fontSize: '0.9rem', color: 'white' }} />
              </ListItemButton>
            </ListItem>
          </List>
        </SwipeableDrawer>

        <PWAInstallPrompt />
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
      </Box>
    );
  }

  // ── DESKTOP: sidebar + fixed appbar layout ──
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
        <Toolbar sx={{ minHeight: 64, px: 3 }}>
          <IconButton color="inherit" edge="start" onClick={() => setMobileOpen((p) => !p)} sx={{ mr: 2, display: { sm: 'none' } }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1, fontWeight: 700, fontSize: '1.1rem' }}>
            Panel de Entrenadores
          </Typography>
          <IconButton color="inherit" onClick={handleOpenCoachMessages} sx={{ mr: 1 }}>
            <Badge badgeContent={unreadCount > 0 ? unreadCount : null} color="error">
              <NotificationsIcon />
            </Badge>
          </IconButton>
          <Avatar sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 'bold' }}>
            {(userInfo?.first_name?.[0] ?? userInfo?.username?.[0] ?? '?').toUpperCase()}{userInfo?.last_name?.[0]?.toUpperCase() ?? ''}
          </Avatar>
        </Toolbar>
      </AppBar>

      {/* PWA install prompt (mobile only) */}
      <PWAInstallPrompt />

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
        <Drawer variant="permanent"
          sx={{
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              borderRight: 'none',
              bgcolor: '#0D1117',
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
        <Toolbar sx={{ minHeight: 64 }} />
        {children}
      </Box>
    </Box>
  );
};

export default Layout;
