import React, { useState } from 'react';
import { useParams, NavLink } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import Divider from '@mui/material/Divider';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import PublicLayout from '../../components/PublicLayout';
import MarkdownRenderer from '../../components/MarkdownRenderer';

// Raw markdown imports — bundled at build time via Vite ?raw
import mdOverview         from '../../content/vendor/README.md?raw';
import mdQuantoryn        from '../../content/vendor/quantoryn-overview.md?raw';
import mdIntegration      from '../../content/vendor/integration-architecture.md?raw';
import mdDataHandling     from '../../content/vendor/data-handling.md?raw';
import mdPrivacy          from '../../content/vendor/privacy-policy.md?raw';
import mdTerms            from '../../content/vendor/terms-of-service.md?raw';
import mdContact          from '../../content/vendor/vendor-contact.md?raw';
import mdDataSpec         from '../../content/vendor/vendor_data_access_spec.md?raw';
import mdChecklist        from '../../content/vendor/vendor_requirements_checklist.md?raw';

const VENDOR_DOCS = {
  '': {
    title: 'Vendor Kit Overview',
    content: mdOverview,
  },
  'quantoryn-overview': {
    title: 'Platform Overview',
    content: mdQuantoryn,
  },
  'integration-architecture': {
    title: 'Integration Architecture',
    content: mdIntegration,
  },
  'data-handling': {
    title: 'Data Handling',
    content: mdDataHandling,
  },
  'data-access-spec': {
    title: 'Data Access Specification',
    content: mdDataSpec,
  },
  'requirements-checklist': {
    title: 'Requirements Checklist',
    content: mdChecklist,
  },
  'privacy-policy': {
    title: 'Privacy Policy (Vendor)',
    content: mdPrivacy,
  },
  'terms-of-service': {
    title: 'Terms of Service (Vendor)',
    content: mdTerms,
  },
  'vendor-contact': {
    title: 'Contact',
    content: mdContact,
  },
};

const SIDEBAR_SECTIONS = [
  {
    heading: 'Overview',
    items: [
      { slug: '',                    label: 'Vendor Kit Index' },
      { slug: 'quantoryn-overview',  label: 'Platform Overview' },
    ],
  },
  {
    heading: 'Technical',
    items: [
      { slug: 'integration-architecture', label: 'Integration Architecture' },
      { slug: 'data-handling',            label: 'Data Handling' },
      { slug: 'data-access-spec',         label: 'Data Access Specification' },
      { slug: 'requirements-checklist',   label: 'Requirements Checklist' },
    ],
  },
  {
    heading: 'Legal & Contacts',
    items: [
      { slug: 'privacy-policy',   label: 'Privacy Policy' },
      { slug: 'terms-of-service', label: 'Terms of Service' },
      { slug: 'vendor-contact',   label: 'Vendor Contact' },
    ],
  },
];

const SIDEBAR_WIDTH = 240;

const SidebarContent = ({ activeSlug, onClose }) => (
  <Box sx={{ width: SIDEBAR_WIDTH, py: 2, height: '100%', overflowY: 'auto' }}>
    <Typography
      sx={{
        px: 2.5,
        pb: 1.5,
        fontSize: '0.7rem',
        fontWeight: 800,
        color: '#F57C00',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
      }}
    >
      Vendor Documentation
    </Typography>

    {SIDEBAR_SECTIONS.map((section, si) => (
      <Box key={si} sx={{ mb: 1 }}>
        <Typography
          sx={{
            px: 2.5,
            py: 0.75,
            fontSize: '0.7rem',
            fontWeight: 700,
            color: '#999',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          {section.heading}
        </Typography>
        {section.items.map(({ slug, label }) => {
          const to = slug ? `/vendor/${slug}` : '/vendor';
          const isActive = activeSlug === slug;
          return (
            <NavLink
              key={slug}
              to={to}
              end={slug === ''}
              onClick={onClose}
              style={{ textDecoration: 'none', display: 'block' }}
            >
              <Box
                sx={{
                  px: 2.5,
                  py: 0.9,
                  fontSize: '0.875rem',
                  fontWeight: isActive ? 700 : 400,
                  color: isActive ? '#F57C00' : '#444',
                  bgcolor: isActive ? 'rgba(245,124,0,0.08)' : 'transparent',
                  borderRight: isActive ? '3px solid #F57C00' : '3px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  '&:hover': {
                    bgcolor: 'rgba(245,124,0,0.05)',
                    color: '#F57C00',
                  },
                }}
              >
                {label}
              </Box>
            </NavLink>
          );
        })}
        {si < SIDEBAR_SECTIONS.length - 1 && <Divider sx={{ mt: 1, mx: 2 }} />}
      </Box>
    ))}
  </Box>
);

const VendorPage = () => {
  const { doc = '' } = useParams();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);

  const current = VENDOR_DOCS[doc] || VENDOR_DOCS[''];

  return (
    <PublicLayout>
      <Box sx={{ display: 'flex', minHeight: 'calc(100vh - 64px)' }}>

        {/* ── DESKTOP SIDEBAR ──────────────────────────── */}
        {!isMobile && (
          <Box
            sx={{
              width: SIDEBAR_WIDTH,
              flexShrink: 0,
              bgcolor: '#fff',
              borderRight: '1px solid #e8e8e8',
              position: 'sticky',
              top: 64,
              alignSelf: 'flex-start',
              height: 'calc(100vh - 64px)',
              overflowY: 'auto',
            }}
          >
            <SidebarContent activeSlug={doc} onClose={() => {}} />
          </Box>
        )}

        {/* ── MOBILE DRAWER ────────────────────────────── */}
        {isMobile && (
          <Drawer
            anchor="left"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
          >
            <SidebarContent activeSlug={doc} onClose={() => setDrawerOpen(false)} />
          </Drawer>
        )}

        {/* ── MAIN CONTENT ─────────────────────────────── */}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          {/* Mobile: nav toggle bar */}
          {isMobile && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 2,
                py: 1.5,
                bgcolor: '#fff',
                borderBottom: '1px solid #e8e8e8',
                position: 'sticky',
                top: 64,
                zIndex: 10,
              }}
            >
              <IconButton
                size="small"
                onClick={() => setDrawerOpen(!drawerOpen)}
                sx={{ color: '#1A2027' }}
                aria-label="toggle sidebar"
              >
                {drawerOpen ? <MenuOpenIcon /> : <MenuIcon />}
              </IconButton>
              <Typography sx={{ fontSize: '0.875rem', color: '#666', fontWeight: 500 }}>
                {current.title}
              </Typography>
            </Box>
          )}

          <Box sx={{ px: { xs: 2, md: 5 }, py: { xs: 4, md: 6 }, maxWidth: 820 }}>
            <Typography
              variant="overline"
              sx={{ color: '#F57C00', fontWeight: 700, letterSpacing: '0.1em', display: 'block', mb: 0.5 }}
            >
              Vendor Documentation
            </Typography>
            <MarkdownRenderer content={current.content} />
          </Box>
        </Box>
      </Box>
    </PublicLayout>
  );
};

export default VendorPage;
