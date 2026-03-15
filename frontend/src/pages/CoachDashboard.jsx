import React, { useState } from 'react';
import { Box, Typography, Paper, Alert, CircularProgress, Chip } from '@mui/material';
import Layout from '../components/Layout';
import RosterSection from '../components/roster/RosterSection';
import AssignmentCalendar from '../components/AssignmentCalendar';
import { useOrg } from '../context/OrgContext';

export default function CoachDashboard() {
  const { activeOrg, orgLoading } = useOrg();
  const [selectedAthleteId, setSelectedAthleteId] = useState(null);

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
        <Alert severity="warning" sx={{ mt: 2 }}>
          No tienes organizaciones asignadas.
        </Alert>
      </Layout>
    );
  }

  return (
    <Layout>
      <Paper sx={{ p: 3, mb: 3, borderRadius: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h5" fontWeight={700}>
            {activeOrg.org_name}
          </Typography>
          <Chip label={activeOrg.role} size="small" color="primary" variant="outlined" />
        </Box>
      </Paper>

      <RosterSection orgId={activeOrg.org_id} onSelectAthlete={setSelectedAthleteId} />
      {selectedAthleteId !== null && (
        <AssignmentCalendar athleteId={selectedAthleteId} orgId={activeOrg.org_id} />
      )}
    </Layout>
  );
}
