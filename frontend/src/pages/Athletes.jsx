import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom'; // <--- IMPORTANTE: Faltaba esto
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Avatar, Chip, IconButton, Button, TextField, InputAdornment,
  CircularProgress, Alert, Tooltip, Snackbar, LinearProgress, useTheme, useMediaQuery,
  Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, Select, FormControl, InputLabel,
} from '@mui/material';
import { Search, Edit, Add, NavigateNext, NotificationsActive, CheckCircle } from '@mui/icons-material';
import Layout from '../components/Layout';
import RiskBadge from '../components/RiskBadge';
import { useOrg } from '../context/OrgContext';
import { listAthletes, listCoaches, updateAthleteCoach } from '../api/p1';
import { getAthleteSubscriptions } from '../api/billing';
import { notifyAthleteDevice } from '../api/roster';
import { getTeamReadiness } from '../api/pmc';

const TSB_ZONE_DOT = {
  overreaching: '#EF4444',
  fatigued:     '#F59E0B',
  productive:   '#3B82F6',
  optimal:      '#22C55E',
  fresh:        '#06B6D4',
};

const SUB_STATUS_CONFIG = {
  active:    { label: 'Activo',    bg: '#ECFDF5', text: '#059669', dot: '#00D4AA' },
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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const { activeOrg, orgLoading } = useOrg();
  const [athletes, setAthletes] = useState([]);
  const [subscriptionMap, setSubscriptionMap] = useState({});
  const [fitnessMap, setFitnessMap] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [subFilter, setSubFilter] = useState('all');
  // PR-141: track notify state per athlete (membership_id → 'idle'|'sent'|'duplicate')
  const [notifyState, setNotifyState] = useState({});
  const [toast, setToast] = useState({ open: false, message: '' });
  // A.1: Coach assignment modal
  const [assignModal, setAssignModal] = useState(null); // null | { athleteId, currentCoachId }
  const [coaches, setCoaches] = useState([]);
  const [selectedCoachId, setSelectedCoachId] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);

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
    const fetchFitness = async () => {
      try {
        const res = await getTeamReadiness();
        const map = {};
        (res.data?.athletes || []).forEach(a => { map[a.membership_id] = a; });
        setFitnessMap(map);
      } catch {
        // Fitness data is supplementary — silent fail
      }
    };
    fetchAthletes();
    fetchSubscriptions();
    fetchFitness();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOrg?.org_id]);

  const openAssignModal = async (athlete) => {
    setSelectedCoachId(athlete.coach_id ?? '');
    setAssignModal({ athleteId: athlete.id, currentCoachId: athlete.coach_id });
    if (coaches.length === 0) {
      try {
        const res = await listCoaches(activeOrg.org_id);
        setCoaches(res.data?.results ?? res.data ?? []);
      } catch {
        // keep empty
      }
    }
  };

  const handleAssignCoach = async () => {
    if (!assignModal) return;
    setAssignSaving(true);
    try {
      await updateAthleteCoach(activeOrg.org_id, assignModal.athleteId, selectedCoachId || null);
      setAthletes((prev) =>
        prev.map((a) => a.id === assignModal.athleteId ? { ...a, coach_id: selectedCoachId || null } : a)
      );
      setToast({ open: true, message: 'Coach asignado correctamente' });
      setAssignModal(null);
    } catch {
      setToast({ open: true, message: 'Error al asignar coach' });
    } finally {
      setAssignSaving(false);
    }
  };

  const handleNotify = useCallback(async (membershipId) => {
    if (!membershipId || notifyState[membershipId]) return;
    setNotifyState(prev => ({ ...prev, [membershipId]: 'loading' }));
    try {
      const res = await notifyAthleteDevice(membershipId);
      const created = res.data?.created;
      const state = created ? 'sent' : 'duplicate';
      setNotifyState(prev => ({ ...prev, [membershipId]: state }));
      setToast({
        open: true,
        message: created ? 'Notificación enviada' : 'Notificación ya enviada',
      });
    } catch {
      setNotifyState(prev => ({ ...prev, [membershipId]: 'idle' }));
    }
  }, [notifyState]);

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
            sx={{ bgcolor: '#00D4AA', color: '#0D1117', '&:hover': { bgcolor: '#00BF99' }, borderRadius: 2, textTransform: 'none', fontWeight: 600 }}
        >
            Nuevo Alumno
        </Button>
      </Box>

      {/* Barra de Búsqueda + Filtros */}
      <Paper sx={{ p: 2, mb: 3, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            sx={{ flex: 1, minWidth: isMobile ? '100%' : 200, width: isMobile ? '100%' : undefined, '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
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

      {/* Mobile card list — xs only */}
      {isMobile && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {filteredAthletes.map((athlete) => {
            const fit = fitnessMap[athlete.membership_id];
            const subStatus = subscriptionMap[athlete.id];
            const subCfg = SUB_STATUS_CONFIG[subStatus];
            const ctl = fit?.ctl ?? null;
            const compliance = ctl && fit?.atl ? Math.round((fit.atl / fit.ctl) * 100) : null;
            return (
              <Paper
                key={athlete.id}
                sx={{ p: 2, borderRadius: 2, cursor: athlete.membership_id ? 'pointer' : 'default' }}
                onClick={() => athlete.membership_id && navigate(`/coach/athletes/${athlete.membership_id}/pmc`)}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                  <Avatar sx={{ bgcolor: '#0EA5E9', color: 'white', width: 36, height: 36, fontSize: '0.85rem', fontWeight: 700 }}>
                    {athlete.first_name ? athlete.first_name.charAt(0) : '?'}
                    {athlete.last_name ? athlete.last_name.charAt(0) : ''}
                  </Avatar>
                  <Box sx={{ flexGrow: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {athlete.first_name} {athlete.last_name}
                    </Typography>
                    {subCfg && (
                      <Chip label={subCfg.label} size="small" sx={{ bgcolor: subCfg.bg, color: subCfg.text, fontWeight: 600, fontSize: '0.7rem', height: 18 }} />
                    )}
                  </Box>
                  {ctl !== null && ctl > 0 && (
                    <Chip label={`CTL ${ctl}`} size="small" sx={{ bgcolor: '#EFF6FF', color: '#2563EB', fontWeight: 700, fontSize: '0.7rem' }} />
                  )}
                </Box>
                {compliance !== null && (
                  <Box>
                    <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600 }}>
                      Cumplimiento: {compliance}%
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={Math.min(compliance, 100)}
                      sx={{ height: 4, borderRadius: 2, mt: 0.5, bgcolor: 'rgba(0,0,0,0.06)', '& .MuiLinearProgress-bar': { bgcolor: compliance >= 80 ? '#22C55E' : compliance >= 60 ? '#F59E0B' : '#EF4444', borderRadius: 2 } }}
                    />
                  </Box>
                )}
              </Paper>
            );
          })}
        </Box>
      )}

      {/* Tabla de Alumnos — sm+ only */}
      <TableContainer component={Paper} sx={{ borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)', display: isMobile ? 'none' : undefined }}>
        <Table>
          <TableHead sx={{ bgcolor: '#F8FAFC' }}>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ATLETA</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ESTADO</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>SUSCRIPCIÓN</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>COACH</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>FITNESS</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>RIESGO</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>DISPOSITIVO</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: '#475569' }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredAthletes.map((athlete) => (
              <TableRow
                key={athlete.id}
                hover
                onClick={() => athlete.membership_id && navigate(`/coach/athletes/${athlete.membership_id}/pmc`)}
                sx={{ cursor: athlete.membership_id ? 'pointer' : 'default' }}
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
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Typography variant="body2" sx={{ color: athlete.coach_id ? '#0F172A' : '#94A3B8', fontSize: '0.82rem' }}>
                      {athlete.coach_name || (athlete.coach_id ? `Coach #${athlete.coach_id}` : '—')}
                    </Typography>
                    <Tooltip title="Asignar coach">
                      <IconButton size="small" onClick={() => openAssignModal(athlete)} sx={{ color: '#94A3B8', '&:hover': { color: '#3b82f6' } }}>
                        <Edit sx={{ fontSize: 14 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </TableCell>
                <TableCell>
                    {(() => {
                      const fit = fitnessMap[athlete.membership_id];
                      if (!fit || fit.ctl === 0) {
                        return <Typography variant="body2" sx={{ color: '#94A3B8' }}>—</Typography>;
                      }
                      const dotColor = TSB_ZONE_DOT[fit.tsb_zone];
                      const acwr = fit.ctl > 0 && fit.atl != null ? fit.atl / fit.ctl : null;
                      const acwrLabel = acwr === null ? 'Sin datos de carga' :
                        acwr > 1.5 ? `ACWR ${acwr.toFixed(2)} — Riesgo alto` :
                        acwr > 1.3 ? `ACWR ${acwr.toFixed(2)} — Precaución` :
                        acwr >= 0.8 ? `ACWR ${acwr.toFixed(2)} — Óptimo` :
                        `ACWR ${acwr.toFixed(2)} — Desentrenamiento`;
                      return (
                        <Tooltip title={acwrLabel}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'default' }}>
                            <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
                              {fit.ctl} CTL
                            </Typography>
                            {dotColor && (
                              <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: dotColor, flexShrink: 0 }} />
                            )}
                          </Box>
                        </Tooltip>
                      );
                    })()}
                </TableCell>
                <TableCell>
                  <RiskBadge risk={athlete.injury_risk} />
                </TableCell>
                <TableCell onClick={e => e.stopPropagation()}>
                  {(() => {
                    const stravaHealth = fitnessMap[athlete.membership_id]?.strava_sync_health;
                    if (stravaHealth === 'healthy') return (
                      <Chip label="Strava" size="small"
                        sx={{ bgcolor: '#ECFDF5', color: '#059669', fontWeight: 600, fontSize: '0.7rem' }} />
                    );
                    if (stravaHealth === 'deferred') return (
                      <Tooltip title="Actividades pendientes de sincronizar">
                        <Chip label="⚠ Strava" size="small"
                          sx={{ bgcolor: '#FFFBEB', color: '#D97706', fontWeight: 600, fontSize: '0.7rem' }} />
                      </Tooltip>
                    );
                    if (stravaHealth === 'disconnected') return (
                      <Chip label="Sin Strava" size="small"
                        sx={{ bgcolor: '#F1F5F9', color: '#94A3B8', fontWeight: 600, fontSize: '0.7rem' }} />
                    );
                    return (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography variant="caption" sx={{ color: '#CBD5E1' }}>—</Typography>
                        {athlete.membership_id && (
                          <Tooltip title={
                            notifyState[athlete.membership_id] === 'sent' ? 'Notificación enviada' :
                            notifyState[athlete.membership_id] === 'duplicate' ? 'Ya notificado' : 'Notificar'
                          }>
                            <span>
                              <IconButton
                                size="small"
                                disabled={!!notifyState[athlete.membership_id]}
                                onClick={() => handleNotify(athlete.membership_id)}
                                sx={{ color: notifyState[athlete.membership_id] ? '#00D4AA' : '#94A3B8' }}
                              >
                                {notifyState[athlete.membership_id] === 'sent' || notifyState[athlete.membership_id] === 'duplicate'
                                  ? <CheckCircle fontSize="small" />
                                  : <NotificationsActive fontSize="small" />}
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                      </Box>
                    );
                  })()}
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={(e) => { e.stopPropagation(); }}>
                    <Edit fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={(e) => { e.stopPropagation(); athlete.membership_id && navigate(`/coach/athletes/${athlete.membership_id}/pmc`); }}
                  >
                    <NavigateNext />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Assign coach modal */}
      <Dialog open={!!assignModal} onClose={() => setAssignModal(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Asignar Coach</DialogTitle>
        <DialogContent>
          <FormControl fullWidth size="small" sx={{ mt: 1 }}>
            <InputLabel>Coach</InputLabel>
            <Select
              value={selectedCoachId}
              label="Coach"
              onChange={(e) => setSelectedCoachId(e.target.value)}
            >
              <MenuItem value="">Sin asignar</MenuItem>
              {coaches.map((c) => {
                const name = `${c.first_name ?? ''} ${c.last_name ?? ''}`.trim() || c.email || `Coach #${c.id}`;
                return <MenuItem key={c.id} value={c.id}>{name}</MenuItem>;
              })}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setAssignModal(null)} sx={{ textTransform: 'none', color: '#64748b' }}>
            Cancelar
          </Button>
          <Button
            variant="contained"
            onClick={handleAssignCoach}
            disabled={assignSaving}
            sx={{ textTransform: 'none', bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, '&:hover': { bgcolor: '#00BF99' } }}
          >
            {assignSaving ? <CircularProgress size={16} sx={{ color: '#0D1117' }} /> : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast.open}
        autoHideDuration={3000}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        message={toast.message}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Layout>
  );
};

export default Athletes;
