import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom'; // <--- IMPORTANTE: Faltaba esto
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Avatar, Chip, IconButton, Button, TextField, InputAdornment,
  CircularProgress, Alert, Tooltip
} from '@mui/material';
import { Search, Edit, Add, NavigateNext } from '@mui/icons-material';
import Layout from '../components/Layout';
import RiskBadge from '../components/RiskBadge';
import { useOrg } from '../context/OrgContext';
import { listAthletes } from '../api/p1';
import { getAthleteSubscriptions } from '../api/billing';

const SUB_STATUS_CONFIG = {
  active:    { label: 'Activo',    bg: '#ECFDF5', text: '#059669', dot: '#10B981' },
  pending:   { label: 'Pendiente', bg: '#FFFBEB', text: '#D97706', dot: '#F59E0B' },
  overdue:   { label: 'Atrasado',  bg: '#FEF2F2', text: '#DC2626', dot: '#EF4444' },
  cancelled: { label: 'Cancelado', bg: '#F1F5F9', text: '#64748B', dot: '#94A3B8' },
  suspended: { label: 'Suspendido',bg: '#F1F5F9', text: '#64748B', dot: '#94A3B8' },
};

function SubBadge({ status }) {
  const cfg = SUB_STATUS_CONFIG[status];
  if (!cfg) return null;
  return (
    <Chip
      label={cfg.label}
      size="small"
      sx={{
        bgcolor: cfg.bg,
        color: cfg.text,
        fontWeight: 600,
        borderRadius: 1,
        fontSize: '0.72rem',
        '& .MuiChip-label': { px: 1 },
      }}
    />
  );
}

const Athletes = () => {
  const navigate = useNavigate();
  const { activeOrg, orgLoading } = useOrg();
  const [athletes, setAthletes] = useState([]);
  const [subscriptionMap, setSubscriptionMap] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [subFilter, setSubFilter] = useState('all');

  useEffect(() => {
    if (!activeOrg) return;
    const fetchAthletes = async () => {
      try {
        const res = await listAthletes(activeOrg.org_id);
        const payload = res.data?.results ?? res.data ?? [];
        setAthletes(Array.isArray(payload) ? payload : []);
      } catch (err) {
        console.error(err);
      }
    };
    const fetchSubscriptions = async () => {
      try {
        const res = await getAthleteSubscriptions();
        const map = {};
        (res.data || []).forEach(sub => { map[sub.athlete_id] = sub.status; });
        setSubscriptionMap(map);
      } catch {
        // Subscription data is supplementary — silent fail
      }
    };
    fetchAthletes();
    fetchSubscriptions();
  }, [activeOrg?.org_id]);

  // Filtro de búsqueda + estado de suscripción
  const safeAthletes = Array.isArray(athletes) ? athletes : [];
  const searchFiltered = safeAthletes.filter(athlete =>
    (athlete.first_name ?? '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (athlete.last_name ?? '').toLowerCase().includes(searchTerm.toLowerCase())
  );
  const filteredAthletes = subFilter === 'all'
    ? searchFiltered
    : searchFiltered.filter(a => subscriptionMap[a.id] === subFilter);

  if (orgLoading) return (
    <Layout><Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box></Layout>
  );
  if (!activeOrg) return (
    <Layout><Alert severity="info" sx={{ m: 4 }}>Sin organización asignada.</Alert></Layout>
  );

  return (
    <Layout>
      {/* Header de la Página */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Mis Alumnos</Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>Gestión integral de atletas.</Typography>
        </Box>
        <Button 
            variant="contained" 
            startIcon={<Add />}
            sx={{ bgcolor: '#F57C00', borderRadius: 2, textTransform: 'none', fontWeight: 600 }}
        >
            Nuevo Alumno
        </Button>
      </Box>

      {/* Barra de Búsqueda + Filtros */}
      <Paper sx={{ p: 2, mb: 3, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            sx={{ flex: 1, minWidth: 200, '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
            placeholder="Buscar por nombre..."
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search sx={{ color: '#94A3B8' }} />
                </InputAdornment>
              ),
            }}
          />
          <Box sx={{ display: 'flex', gap: 0.5, bgcolor: '#F1F5F9', borderRadius: 1.5, p: 0.5 }}>
            {[
              { key: 'all', label: 'Todos' },
              { key: 'active', label: 'Activos' },
              { key: 'pending', label: 'Pendientes' },
              { key: 'overdue', label: 'Atrasados' },
            ].map(({ key, label }) => (
              <Button
                key={key}
                onClick={() => setSubFilter(key)}
                size="small"
                sx={{
                  px: 1.5, py: 0.5, minWidth: 0, borderRadius: 1,
                  fontSize: '0.78rem', fontWeight: subFilter === key ? 600 : 400,
                  textTransform: 'none',
                  bgcolor: subFilter === key ? 'white' : 'transparent',
                  color: subFilter === key ? '#0F172A' : '#64748B',
                  boxShadow: subFilter === key ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  '&:hover': { bgcolor: subFilter === key ? 'white' : 'rgba(255,255,255,0.6)' },
                }}
              >
                {label}
              </Button>
            ))}
          </Box>
        </Box>
      </Paper>

      {/* Tabla de Alumnos */}
      <TableContainer component={Paper} sx={{ borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
        <Table>
          <TableHead sx={{ bgcolor: '#F8FAFC' }}>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ATLETA</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ESTADO</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>SUSCRIPCIÓN</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>PLAN</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>FITNESS</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>RIESGO</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: '#475569' }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredAthletes.map((athlete) => (
              <TableRow 
                key={athlete.id} 
                hover
                onClick={() => navigate(`/athletes/${athlete.id}`)} // <--- AQUÍ ESTÁ LA MAGIA DEL CLIC
                sx={{ cursor: 'pointer' }} // <--- Cambia el cursor a manita
              >
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Avatar sx={{ bgcolor: '#0EA5E9', mr: 2, width: 32, height: 32, fontSize: '0.875rem' }}>
                      {athlete.first_name ? athlete.first_name.charAt(0) : '?'}
                      {athlete.last_name ? athlete.last_name.charAt(0) : ''}
                    </Avatar>
                    <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{athlete.first_name} {athlete.last_name}</Typography>
                    </Box>
                  </Box>
                </TableCell>
                <TableCell>
                    <Chip
                        label={athlete.is_active !== false ? "Activo" : "Inactivo"}
                        size="small"
                        sx={{
                            bgcolor: athlete.is_active !== false ? '#ECFDF5' : '#F1F5F9',
                            color: athlete.is_active !== false ? '#059669' : '#64748B',
                            fontWeight: 600,
                            borderRadius: 1
                        }}
                    />
                </TableCell>
                <TableCell>
                    <SubBadge status={subscriptionMap[athlete.id]} />
                </TableCell>
                <TableCell>
                    <Typography variant="body2" sx={{ color: '#475569' }}>
                        Trail Elite
                    </Typography>
                </TableCell>
                <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
                        {/* Dato simulado hasta tener real */}
                        {(((athlete.id || 1) * 7) % 50) + 40} CTL
                    </Typography>
                </TableCell>
                <TableCell>
                  <RiskBadge risk={athlete.injury_risk} />
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={(e) => { e.stopPropagation(); /* Evita navegar al editar */ }}>
                    <Edit fontSize="small" />
                  </IconButton>
                  <IconButton size="small">
                    <NavigateNext />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Layout>
  );
};

export default Athletes;
