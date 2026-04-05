import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  CircularProgress,
  Chip,
  Button,
  Tooltip,
} from '@mui/material';
import LinkIcon from '@mui/icons-material/Link';
import EditIcon from '@mui/icons-material/Edit';
import { Building2 } from 'lucide-react';
import Layout from '../components/Layout';
import RosterSection from '../components/roster/RosterSection';
import AssignmentCalendar from '../components/AssignmentCalendar';
import ManageConnectionsModal from '../components/roster/ManageConnectionsModal';
import OrgProfileEditModal from '../components/OrgProfileEditModal';
import { useOrg } from '../context/OrgContext';
import { listExternalIdentities, getOrgProfile } from '../api/p1';
import { getCoachBriefing } from '../api/teams';

// ── Coach Briefing Card (PR-148) ──────────────────────────────────────────────

function CoachBriefingCard({ orgId }) {
  const [briefing, setBriefing] = React.useState(null);

  React.useEffect(() => {
    if (!orgId) return;
    getCoachBriefing(orgId)
      .then((res) => setBriefing(res.data))
      .catch(() => {});
  }, [orgId]);

  if (!briefing || briefing.athletes_total === 0) return null;

  const dateLabel = briefing.yesterday_date
    ? new Date(briefing.yesterday_date + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
    : '';

  const rows = [
    {
      icon: '✅',
      text: `${briefing.athletes_trained_yesterday}/${briefing.athletes_total} atletas entrenaron`,
    },
    briefing.athletes_overloaded > 0 && {
      icon: '🔵',
      text: `${briefing.athletes_overloaded} con sobrecarga esta semana`,
    },
    briefing.athletes_inactive_4d > 0 && {
      icon: '⚠️',
      text: `${briefing.athletes_inactive_4d} sin actividad (4+ días)`,
    },
    briefing.unread_messages > 0 && {
      icon: '💬',
      text: `${briefing.unread_messages} mensaje${briefing.unread_messages !== 1 ? 's' : ''} sin leer`,
    },
  ].filter(Boolean);

  return (
    <Paper
      sx={{
        p: 2.5, mb: 3, borderRadius: 3,
        border: '1px solid', borderColor: 'divider',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        borderLeft: '4px solid #00D4AA',
      }}
    >
      <Typography variant="subtitle2" fontWeight={700} color="text.primary" sx={{ mb: 1.5 }}>
        Resumen de Ayer — {dateLabel}
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        {rows.map((row, i) => (
          <Typography key={i} variant="body2" color="text.secondary">
            {row.icon} {row.text}
          </Typography>
        ))}
      </Box>
    </Paper>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function CoachDashboard() {
  const { activeOrg, orgLoading } = useOrg();
  const [selectedAthleteId, setSelectedAthleteId] = useState(null);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [activeConnectionCount, setActiveConnectionCount] = useState(null);
  const [orgProfile, setOrgProfile] = useState(null);
  const [profileEditOpen, setProfileEditOpen] = useState(false);

  const isOwnerOrAdmin = activeOrg?.role === 'owner' || activeOrg?.role === 'admin';

  const loadOrgProfile = () => {
    if (!activeOrg?.org_id) return;
    getOrgProfile(activeOrg.org_id)
      .then((res) => setOrgProfile(res.data))
      .catch(() => {});
  };

  useEffect(() => {
    if (!activeOrg) return;
    listExternalIdentities(activeOrg.org_id)
      .then((res) => {
        const identities = res.data?.results ?? res.data ?? [];
        setActiveConnectionCount(identities.filter((i) => i.status === 'linked').length);
      })
      .catch(() => setActiveConnectionCount(null));
    loadOrgProfile();
  }, [activeOrg]); // eslint-disable-line react-hooks/exhaustive-deps

  if (orgLoading) {
    return (
      <Layout>
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress />
        </Box>
      </Layout>
    );
  }

  if (!activeOrg) {
    return (
      <Layout>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 16,
            textAlign: 'center',
          }}
        >
          <Building2 style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }} />
          <Typography variant="h6" fontWeight={600} color="text.primary" gutterBottom>
            Sin organización asignada
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Contacta a tu administrador para que te asigne a una organización.
          </Typography>
        </Box>
      </Layout>
    );
  }

  return (
    <Layout>
      {/* PR-165b: Org profile header */}
      <Paper
        sx={{
          mb: 3, borderRadius: 3,
          background: 'linear-gradient(135deg, #0D1117 0%, #1a2332 100%)',
          border: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '0 4px 12px 0 rgba(0,0,0,0.15)',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ p: 3 }}>
          {/* Top row: logo + name + role + edit */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, mb: orgProfile?.description ? 1.5 : 0 }}>
            {/* Logo placeholder */}
            <Box
              sx={{
                width: 52, height: 52, borderRadius: 2, flexShrink: 0,
                bgcolor: '#00D4AA', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Typography sx={{ color: '#0D1117', fontWeight: 800, fontSize: '1.1rem' }}>
                {(activeOrg.org_name || 'O').slice(0, 2).toUpperCase()}
              </Typography>
            </Box>

            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
                <Typography variant="h5" sx={{ fontWeight: 700, color: '#F8FAFC' }}>
                  {activeOrg.org_name}
                </Typography>
                <Chip
                  label={activeOrg.role}
                  size="small"
                  variant="outlined"
                  sx={{ borderColor: '#00D4AA', color: '#00D4AA', fontWeight: 600 }}
                />
              </Box>
              {orgProfile?.description && (
                <Typography variant="body2" sx={{ color: '#94A3B8', mt: 0.5 }}>
                  {orgProfile.description}
                </Typography>
              )}
              {/* City / disciplines / year row */}
              {orgProfile && (orgProfile.city || orgProfile.disciplines || orgProfile.founded_year) && (
                <Box sx={{ display: 'flex', gap: 2, mt: 0.75, flexWrap: 'wrap' }}>
                  {orgProfile.city && (
                    <Typography variant="caption" sx={{ color: '#64748B' }}>
                      📍 {orgProfile.city}
                    </Typography>
                  )}
                  {orgProfile.disciplines && (
                    <Typography variant="caption" sx={{ color: '#64748B' }}>
                      🏃 {orgProfile.disciplines}
                    </Typography>
                  )}
                  {orgProfile.founded_year && (
                    <Typography variant="caption" sx={{ color: '#64748B' }}>
                      📅 Desde {orgProfile.founded_year}
                    </Typography>
                  )}
                </Box>
              )}
            </Box>

            {/* Actions */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0, flexWrap: 'wrap' }}>
              {isOwnerOrAdmin && (
                <Tooltip title="Editar perfil">
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<EditIcon />}
                    onClick={() => setProfileEditOpen(true)}
                    sx={{
                      color: '#94A3B8', borderColor: 'rgba(255,255,255,0.15)',
                      textTransform: 'none', fontSize: '0.75rem',
                      '&:hover': { borderColor: '#00D4AA', color: '#00D4AA' },
                    }}
                  >
                    Editar perfil
                  </Button>
                </Tooltip>
              )}
              {activeConnectionCount !== null && (
                <Chip
                  label={
                    activeConnectionCount > 0
                      ? `${activeConnectionCount} conexión${activeConnectionCount !== 1 ? 'es' : ''} activa${activeConnectionCount !== 1 ? 's' : ''}`
                      : 'Sin conexiones activas'
                  }
                  size="small"
                  color={activeConnectionCount > 0 ? 'success' : 'default'}
                  variant="outlined"
                  sx={{ borderColor: 'rgba(255,255,255,0.2)', color: '#94A3B8' }}
                />
              )}
              <Button
                size="small"
                variant="outlined"
                startIcon={<LinkIcon />}
                onClick={() => setConnectionsOpen(true)}
                sx={{
                  color: '#00D4AA', borderColor: '#00D4AA',
                  '&:hover': { borderColor: '#00BF99', bgcolor: 'rgba(0,212,170,0.08)' },
                }}
              >
                Conexiones
              </Button>
            </Box>
          </Box>
        </Box>
      </Paper>

      {/* Org profile edit modal */}
      <OrgProfileEditModal
        open={profileEditOpen}
        onClose={() => setProfileEditOpen(false)}
        orgId={activeOrg.org_id}
        initialData={orgProfile}
        onSaved={loadOrgProfile}
      />

      {/* PR-148: Morning briefing card */}
      <CoachBriefingCard orgId={activeOrg.org_id} />

      {/* Roster */}
      <RosterSection orgId={activeOrg.org_id} onSelectAthlete={setSelectedAthleteId} userRole={activeOrg.role} />

      {selectedAthleteId !== null && (
        <AssignmentCalendar athleteId={selectedAthleteId} orgId={activeOrg.org_id} />
      )}

      <ManageConnectionsModal
        open={connectionsOpen}
        onClose={() => setConnectionsOpen(false)}
        orgId={activeOrg.org_id}
      />
    </Layout>
  );
}
