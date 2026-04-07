import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Grid, Chip, CircularProgress,
} from '@mui/material';
import { People, CreditCard, Link as LinkIcon } from '@mui/icons-material';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import client from '../api/client';

export default function StaffDashboard() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id;

  const [stats, setStats] = useState({ athletes: 0, active_subs: 0, pending_subs: 0 });
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState('');

  useEffect(() => {
    client.get('/api/me')
      .then((res) => {
        const name = res.data.first_name || res.data.username || 'Staff';
        setUserName(name);
      })
      .catch(() => {});
  }, [activeOrg?.org_id]);

  useEffect(() => {
    if (!orgId) return;
    Promise.all([
      client.get(`/api/p1/orgs/${orgId}/roster/athletes/`).catch(() => ({ data: [] })),
      client.get('/api/billing/athlete-subscriptions/').catch(() => ({ data: [] })),
    ]).then(([athletesRes, subsRes]) => {
      const athletes = athletesRes.data?.results ?? athletesRes.data ?? [];
      const subs = subsRes.data?.results ?? subsRes.data ?? [];
      setStats({
        athletes: athletes.length,
        active_subs: subs.filter((s) => s.status === 'active').length,
        pending_subs: subs.filter((s) => s.status === 'pending' || s.status === 'overdue').length,
      });
    }).finally(() => setLoading(false));
  }, [orgId]);

  const kpiCards = [
    { label: 'Atletas', value: stats.athletes, icon: <People sx={{ color: '#00D4AA' }} />, color: 'rgba(0,212,170,0.08)' },
    { label: 'Suscripciones activas', value: stats.active_subs, icon: <CreditCard sx={{ color: '#3b82f6' }} />, color: 'rgba(59,130,246,0.08)' },
    { label: 'Pagos pendientes', value: stats.pending_subs, icon: <LinkIcon sx={{ color: '#f59e0b' }} />, color: 'rgba(245,158,11,0.08)' },
  ];

  return (
    <Layout>
      <Box sx={{ p: { xs: 2, sm: 3 } }}>
        {/* Header */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>
            Panel de Administración
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Hola, {userName} — {activeOrg?.org_name}
            <Chip label="Staff" size="small" sx={{ ml: 1, bgcolor: 'rgba(139,92,246,0.1)', color: '#8b5cf6', fontWeight: 700, fontSize: '0.7rem' }} />
          </Typography>
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
            <CircularProgress sx={{ color: '#00D4AA' }} />
          </Box>
        ) : (
          <Grid container spacing={2} sx={{ mb: 4 }}>
            {kpiCards.map((card) => (
              <Grid item xs={12} sm={4} key={card.label}>
                <Paper sx={{ p: 2.5, borderRadius: 3, border: '1px solid #e2e8f0', bgcolor: card.color }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    {card.icon}
                    <Box>
                      <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A', lineHeight: 1 }}>
                        {card.value}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#64748B' }}>
                        {card.label}
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Layout>
  );
}
