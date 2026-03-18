import React, { useEffect, useState } from 'react';
import { Box, Typography, Paper, Alert, CircularProgress, Chip, Button } from '@mui/material';
import LinkIcon from '@mui/icons-material/Link';
import { Building2 } from 'lucide-react';
import Layout from '../components/Layout';
import RosterSection from '../components/roster/RosterSection';
import AssignmentCalendar from '../components/AssignmentCalendar';
import ManageConnectionsModal from '../components/roster/ManageConnectionsModal';
import { useOrg } from '../context/OrgContext';
import { listExternalIdentities } from '../api/p1';

export default function CoachDashboard() {
  const { activeOrg, orgLoading } = useOrg();
  const [selectedAthleteId, setSelectedAthleteId] = useState(null);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [activeConnectionCount, setActiveConnectionCount] = useState(null);

  useEffect(() => {
    if (!activeOrg) return;
    listExternalIdentities(activeOrg.org_id)
      .then((res) => {
        const identities = res.data?.results ?? res.data ?? [];
        setActiveConnectionCount(identities.filter((i) => i.status === 'linked').length);
      })
      .catch(() => setActiveConnectionCount(null));
  }, [activeOrg]);

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
      <Paper
        sx={{
          p: 3,
          mb: 3,
          borderRadius: 3,
          border: '1px solid',
          borderColor: 'divider',
          boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            flexWrap: 'wrap',
            justifyContent: 'space-between',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <Typography variant="h5" fontWeight={700}>
              {activeOrg.org_name}
            </Typography>
            <Chip
              label={activeOrg.role}
              size="small"
              variant="outlined"
              sx={{ borderColor: '#F57C00', color: '#F57C00', fontWeight: 600 }}
            />
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
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
              />
            )}
            <Button
              size="small"
              variant="outlined"
              startIcon={<LinkIcon />}
              onClick={() => setConnectionsOpen(true)}
              sx={{
                color: '#F57C00',
                borderColor: '#F57C00',
                '&:hover': { borderColor: '#e65100', bgcolor: 'rgba(245,124,0,0.04)' },
              }}
            >
              Gestionar Conexiones
            </Button>
          </Box>
        </Box>
      </Paper>

      <RosterSection orgId={activeOrg.org_id} onSelectAthlete={setSelectedAthleteId} />

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
