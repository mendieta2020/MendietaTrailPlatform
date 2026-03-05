import React, { useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import MenuIcon from '@mui/icons-material/Menu';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';

const NAV_LINKS = [
  { label: 'Privacy', to: '/privacy' },
  { label: 'Terms', to: '/terms' },
  { label: 'Security', to: '/security' },
  { label: 'Vendor Docs', to: '/vendor' },
];

const navLinkStyle = (isActive) => ({
  color: isActive ? '#F57C00' : '#1A2027',
  fontWeight: isActive ? 700 : 500,
  textDecoration: 'none',
  fontSize: '0.9rem',
  padding: '6px 12px',
  borderRadius: '8px',
  transition: 'background 0.15s',
  '&:hover': { bgcolor: 'rgba(245,124,0,0.08)' },
});

/**
 * Shared layout for all public (unauthenticated) pages.
 * Top nav → content → footer.
 */
const PublicLayout = ({ children }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  const drawer = (
    <Box sx={{ width: 260 }} role="presentation" onClick={() => setDrawerOpen(false)}>
      <Box sx={{ p: 2.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box
          sx={{
            width: 28,
            height: 28,
            borderRadius: '8px',
            bgcolor: '#F57C00',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.75rem', lineHeight: 1 }}>Q</Typography>
        </Box>
        <Typography sx={{ fontWeight: 800, fontSize: '1.1rem', color: '#1A2027' }}>Quantoryn</Typography>
      </Box>
      <Divider />
      <List>
        {NAV_LINKS.map(({ label, to }) => (
          <ListItem key={to} disablePadding>
            <ListItemButton
              component={Link}
              to={to}
              selected={location.pathname.startsWith(to)}
              sx={{
                '&.Mui-selected': { color: '#F57C00', fontWeight: 700 },
              }}
            >
              <ListItemText primary={label} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Button
          component={Link}
          to="/login"
          variant="contained"
          fullWidth
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
        >
          Login
        </Button>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: '#f9fafb' }}>
      {/* ── TOP NAV ──────────────────────────────────────── */}
      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          bgcolor: '#fff',
          borderBottom: '1px solid #e8e8e8',
          color: '#1A2027',
        }}
      >
        <Toolbar sx={{ gap: 1, px: { xs: 2, md: 4 } }}>
          {/* Logo */}
          <Box
            component={Link}
            to="/"
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              textDecoration: 'none',
              mr: 3,
              flexShrink: 0,
            }}
          >
            <Box
              sx={{
                width: 32,
                height: 32,
                borderRadius: '10px',
                bgcolor: '#F57C00',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.85rem', lineHeight: 1 }}>Q</Typography>
            </Box>
            <Typography sx={{ fontWeight: 800, fontSize: '1.15rem', color: '#1A2027', letterSpacing: '-0.01em' }}>
              Quantoryn
            </Typography>
          </Box>

          {/* Desktop nav links */}
          {!isMobile && (
            <Box sx={{ display: 'flex', gap: 0.5, flexGrow: 1 }}>
              {NAV_LINKS.map(({ label, to }) => (
                <NavLink
                  key={to}
                  to={to}
                  style={{ textDecoration: 'none' }}
                >
                  {({ isActive }) => (
                    <Box sx={navLinkStyle(isActive)}>{label}</Box>
                  )}
                </NavLink>
              ))}
            </Box>
          )}

          {isMobile && <Box sx={{ flexGrow: 1 }} />}

          {/* Login button */}
          {!isMobile && (
            <Button
              component={Link}
              to="/login"
              variant="outlined"
              size="small"
              sx={{
                borderColor: '#F57C00',
                color: '#F57C00',
                fontWeight: 600,
                borderRadius: '8px',
                '&:hover': { bgcolor: 'rgba(245,124,0,0.06)', borderColor: '#F57C00' },
              }}
            >
              Login
            </Button>
          )}

          {/* Mobile hamburger */}
          {isMobile && (
            <IconButton
              edge="end"
              onClick={() => setDrawerOpen(true)}
              sx={{ color: '#1A2027' }}
              aria-label="open navigation menu"
            >
              <MenuIcon />
            </IconButton>
          )}
        </Toolbar>
      </AppBar>

      {/* Mobile drawer */}
      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        {drawer}
      </Drawer>

      {/* ── MAIN CONTENT ─────────────────────────────────── */}
      <Box component="main" sx={{ flexGrow: 1 }}>
        {children}
      </Box>

      {/* ── FOOTER ───────────────────────────────────────── */}
      <Box
        component="footer"
        sx={{
          bgcolor: '#1A2027',
          color: 'rgba(255,255,255,0.7)',
          py: 4,
          px: { xs: 2, md: 4 },
          mt: 'auto',
        }}
      >
        <Box
          sx={{
            maxWidth: 1100,
            mx: 'auto',
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: 2,
          }}
        >
          <Box>
            <Typography sx={{ fontWeight: 700, color: '#fff', fontSize: '0.95rem', mb: 0.5 }}>
              Quantoryn
            </Typography>
            <Typography sx={{ fontSize: '0.8rem' }}>
              Endurance Training Platform · Córdoba, Argentina
            </Typography>
            <Typography sx={{ fontSize: '0.8rem', mt: 0.5 }}>
              © {new Date().getFullYear()} Quantoryn. All rights reserved.
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {[
              { label: 'Partnerships', email: 'partnerships@quantoryn.com' },
              { label: 'Support', email: 'support@quantoryn.com' },
              { label: 'Security', email: 'security@quantoryn.com' },
            ].map(({ label, email }) => (
              <Typography key={email} sx={{ fontSize: '0.8rem' }}>
                <Box component="span" sx={{ color: 'rgba(255,255,255,0.5)', mr: 0.75 }}>
                  {label}
                </Box>
                <Box
                  component="a"
                  href={`mailto:${email}`}
                  sx={{ color: '#F57C00', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
                >
                  {email}
                </Box>
              </Typography>
            ))}
          </Box>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            {[
              { label: 'Privacy', to: '/privacy' },
              { label: 'Terms', to: '/terms' },
              { label: 'Security', to: '/security' },
              { label: 'Vendor Docs', to: '/vendor' },
            ].map(({ label, to }) => (
              <Box
                key={to}
                component={Link}
                to={to}
                sx={{ color: 'rgba(255,255,255,0.65)', textDecoration: 'none', fontSize: '0.8rem', '&:hover': { color: '#F57C00' } }}
              >
                {label}
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default PublicLayout;
