import React from 'react';
import { Link } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import PublicLayout from '../../components/PublicLayout';

const PILLARS = [
  {
    icon: '🧬',
    title: 'Scientific Core',
    body: 'Training load modelled as TSS, TRIMP, and RPE. PMC (CTL/ATL/TSB) and injury risk computed from canonical load, not guesses.',
  },
  {
    icon: '🏢',
    title: 'Multi-tenant, Fail-closed',
    body: 'Every data record is scoped to a coach organisation. Cross-organisation access is architecturally impossible, not just policy-controlled.',
  },
  {
    icon: '🔌',
    title: 'Provider-agnostic',
    body: 'Provider-specific logic is fully isolated. Adding a new provider requires zero changes to domain models or analytics.',
  },
  {
    icon: '📐',
    title: 'Plan ≠ Real',
    body: 'Planned workouts and completed activities are separate domain objects. Reconciliation is explicit, versioned, and reversible.',
  },
  {
    icon: '🔒',
    title: 'Security by Design',
    body: 'HMAC-signed OAuth state, single-use nonces, tokens never logged, rate limiting on all surfaces, tenant isolation enforced at the DB layer.',
  },
  {
    icon: '♻️',
    title: 'Reproducible Analytics',
    body: 'Raw provider payloads preserved for audit. All load calculations are versioned. Recalculating with a new algorithm never destroys history.',
  },
];

const PillarCard = ({ icon, title, body }) => (
  <Box
    sx={{
      bgcolor: '#fff',
      border: '1px solid #e8e8e8',
      borderRadius: 3,
      p: 3,
      height: '100%',
      transition: 'box-shadow 0.2s',
      '&:hover': { boxShadow: '0 4px 24px rgba(0,0,0,0.08)' },
    }}
  >
    <Typography sx={{ fontSize: '1.8rem', mb: 1.5, lineHeight: 1 }}>{icon}</Typography>
    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1, color: '#1A2027' }}>
      {title}
    </Typography>
    <Typography variant="body2" sx={{ color: '#555', lineHeight: 1.7 }}>
      {body}
    </Typography>
  </Box>
);

const LandingPage = () => (
  <PublicLayout>
    {/* ── HERO ─────────────────────────────────────────── */}
    <Box
      sx={{
        background: 'linear-gradient(135deg, #1A2027 0%, #2d3748 100%)',
        color: '#fff',
        py: { xs: 8, md: 12 },
        px: { xs: 2, md: 4 },
        textAlign: 'center',
      }}
    >
      <Box sx={{ maxWidth: 720, mx: 'auto' }}>
        <Box
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.75,
            bgcolor: 'rgba(245,124,0,0.15)',
            border: '1px solid rgba(245,124,0,0.3)',
            borderRadius: '20px',
            px: 2,
            py: 0.5,
            mb: 3,
          }}
        >
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#F57C00' }} />
          <Typography sx={{ fontSize: '0.8rem', color: '#F57C00', fontWeight: 600, letterSpacing: '0.05em' }}>
            ENDURANCE TRAINING PLATFORM · CÓRDOBA, ARGENTINA
          </Typography>
        </Box>

        <Typography
          variant="h2"
          sx={{ fontWeight: 800, fontSize: { xs: '2rem', md: '3rem' }, mb: 2, lineHeight: 1.15, letterSpacing: '-0.02em' }}
        >
          A Scientific Operating System for Endurance Coaching
        </Typography>

        <Typography
          sx={{ fontSize: { xs: '1rem', md: '1.2rem' }, color: 'rgba(255,255,255,0.7)', mb: 4, lineHeight: 1.7 }}
        >
          Quantoryn connects coach intent with athlete execution.
          Plan vs Real reconciliation. Evidence-based load analytics.
          Provider-agnostic integrations. Strict multi-tenant isolation.
        </Typography>

        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Button
            component="a"
            href="https://app.quantoryn.com"
            variant="contained"
            size="large"
            sx={{
              bgcolor: '#F57C00',
              '&:hover': { bgcolor: '#e65100' },
              px: 4,
              fontWeight: 700,
              borderRadius: '10px',
            }}
          >
            Login to Platform →
          </Button>
          <Button
            component={Link}
            to="/vendor"
            variant="outlined"
            size="large"
            sx={{
              borderColor: 'rgba(255,255,255,0.4)',
              color: '#fff',
              px: 4,
              fontWeight: 600,
              borderRadius: '10px',
              '&:hover': { borderColor: '#F57C00', color: '#F57C00', bgcolor: 'transparent' },
            }}
          >
            Vendor Documentation
          </Button>
        </Box>
      </Box>
    </Box>

    {/* ── PROVIDER BADGE ───────────────────────────────── */}
    <Box sx={{ bgcolor: '#f9fafb', borderBottom: '1px solid #e8e8e8', py: 2, px: 4, textAlign: 'center' }}>
      <Typography sx={{ fontSize: '0.8rem', color: '#888', mb: 1, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Integration status
      </Typography>
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 3, flexWrap: 'wrap' }}>
        {[
          { name: 'Strava', status: 'Live', color: '#FC4C02' },
          { name: 'Garmin', status: 'Under partnership review', color: '#888' },
          { name: 'COROS', status: 'Under partnership review', color: '#888' },
          { name: 'Polar', status: 'Under partnership review', color: '#888' },
          { name: 'Suunto', status: 'Under partnership review', color: '#888' },
          { name: 'Wahoo', status: 'Under partnership review', color: '#888' },
        ].map(({ name, status, color }) => (
          <Box key={name} sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color }} />
            <Typography sx={{ fontSize: '0.85rem', fontWeight: 600, color: '#1A2027' }}>{name}</Typography>
            <Typography sx={{ fontSize: '0.75rem', color: color }}>{status}</Typography>
          </Box>
        ))}
      </Box>
    </Box>

    {/* ── PILLARS ──────────────────────────────────────── */}
    <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 6, md: 10 } }}>
      <Typography
        variant="h4"
        sx={{ fontWeight: 800, textAlign: 'center', mb: 1, color: '#1A2027' }}
      >
        Architecture Principles
      </Typography>
      <Typography
        sx={{ textAlign: 'center', color: '#666', mb: 6, fontSize: '1rem' }}
      >
        Not a social network. Not a consumer app. A private, evidence-based coaching system.
      </Typography>

      <Grid container spacing={3}>
        {PILLARS.map((p) => (
          <Grid key={p.title} size={{ xs: 12, sm: 6, md: 4 }}>
            <PillarCard {...p} />
          </Grid>
        ))}
      </Grid>
    </Box>

    {/* ── COMPLIANCE CTA ───────────────────────────────── */}
    <Box
      sx={{
        bgcolor: '#fff',
        borderTop: '1px solid #e8e8e8',
        borderBottom: '1px solid #e8e8e8',
        py: { xs: 5, md: 8 },
        px: { xs: 2, md: 4 },
        textAlign: 'center',
      }}
    >
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1, color: '#1A2027' }}>
        API & Vendor Partnerships
      </Typography>
      <Typography sx={{ color: '#666', mb: 4, maxWidth: 560, mx: 'auto' }}>
        Pursuing API partnerships for additional provider integrations?
        Our vendor documentation covers architecture, security posture, data handling, and integration specifications.
      </Typography>
      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
        <Button
          component={Link}
          to="/vendor"
          variant="contained"
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' }, borderRadius: '10px', fontWeight: 700, px: 3 }}
        >
          View Vendor Kit
        </Button>
        <Button
          component={Link}
          to="/privacy"
          variant="outlined"
          sx={{ borderColor: '#e0e0e0', color: '#555', borderRadius: '10px', px: 3, '&:hover': { borderColor: '#F57C00', color: '#F57C00' } }}
        >
          Privacy Policy
        </Button>
        <Button
          component={Link}
          to="/terms"
          variant="outlined"
          sx={{ borderColor: '#e0e0e0', color: '#555', borderRadius: '10px', px: 3, '&:hover': { borderColor: '#F57C00', color: '#F57C00' } }}
        >
          Terms of Service
        </Button>
        <Button
          component={Link}
          to="/security"
          variant="outlined"
          sx={{ borderColor: '#e0e0e0', color: '#555', borderRadius: '10px', px: 3, '&:hover': { borderColor: '#F57C00', color: '#F57C00' } }}
        >
          Security Policy
        </Button>
      </Box>
    </Box>
  </PublicLayout>
);

export default LandingPage;
