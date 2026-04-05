import React, { useReducer, useEffect, useState } from 'react';
import {
  Tabs, Tab, Box, Grid, CircularProgress, Alert, Typography,
  Button, Avatar, Chip,
} from '@mui/material';
import { Users, UserCheck, Users2 } from 'lucide-react';
import { listAthletes, listCoaches, listTeamInvitations, deleteTeamInvitation } from '../../api/p1';
import AthleteCard from './AthleteCard';
import CoachCard from './CoachCard';
import InviteTeamModal from './InviteTeamModal';

const ROLE_COLORS = {
  owner: '#00D4AA',
  coach: '#3b82f6',
  staff: '#8b5cf6',
  athlete: '#64748b',
};

const initialState = {
  loading: false,
  error: null,
  athletes: [],
  coaches: [],
  teamMembers: [],
  pendingInvites: [],
};

function rosterReducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':
      return { ...state, loading: true, error: null };
    case 'FETCH_SUCCESS':
      return {
        loading: false,
        error: null,
        athletes: action.athletes,
        coaches: action.coaches,
        teamMembers: action.teamMembers,
        pendingInvites: action.pendingInvites,
      };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    case 'ADD_INVITE':
      return { ...state, pendingInvites: [action.invite, ...state.pendingInvites] };
    case 'REMOVE_INVITE':
      return { ...state, pendingInvites: state.pendingInvites.filter((i) => i.id !== action.id) };
    default:
      return state;
  }
}

export default function RosterSection({ orgId, onSelectAthlete, userRole }) {
  const [tab, setTab] = React.useState(0);
  const [state, dispatch] = useReducer(rosterReducer, initialState);
  const [inviteModal, setInviteModal] = useState(null); // null | 'coach' | 'staff'

  const isOwner = userRole === 'owner';

  useEffect(() => {
    if (!orgId) return;
    dispatch({ type: 'FETCH_START' });

    const promises = [
      listAthletes(orgId),
      listCoaches(orgId),
    ];
    if (isOwner) {
      promises.push(listTeamInvitations(orgId));
    }

    Promise.all(promises)
      .then(([athletesRes, coachesRes, invitesRes]) => {
        const athletes = athletesRes.data?.results ?? athletesRes.data ?? [];
        const coaches  = coachesRes.data?.results  ?? coachesRes.data  ?? [];

        // Build team members list from coaches
        const members = coaches.map((c) => ({
          id: `coach-${c.id}`,
          name: c.user?.name || c.user?.username || `Coach #${c.id}`,
          email: c.user?.email || '',
          role: 'coach',
          status: 'active',
        }));

        const pendingInvites = invitesRes
          ? (invitesRes.data?.results ?? invitesRes.data ?? []).filter((i) => i.status === 'pending')
          : [];

        dispatch({
          type: 'FETCH_SUCCESS',
          athletes,
          coaches,
          teamMembers: members,
          pendingInvites,
        });
      })
      .catch(() =>
        dispatch({
          type: 'FETCH_ERROR',
          error: 'No se pudo cargar el roster. Intenta de nuevo.',
        })
      );
  }, [orgId, isOwner]);

  const handleInviteCreated = (invite) => {
    dispatch({ type: 'ADD_INVITE', invite });
  };

  const handleRevokeInvite = async (invId) => {
    if (!window.confirm('¿Revocar esta invitación?')) return;
    try {
      await deleteTeamInvitation(orgId, invId);
      dispatch({ type: 'REMOVE_INVITE', id: invId });
    } catch {
      // ignore — invitation may already be gone
    }
  };

  if (state.loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (state.error) {
    return <Alert severity="error" sx={{ mt: 2 }}>{state.error}</Alert>;
  }

  const standardTabs = [
    { label: 'Atletas', items: state.athletes, Card: AthleteCard, prop: 'athlete', emptyTitle: 'No hay atletas aún', emptySubtitle: 'Agrega atletas a la organización usando "Gestionar Conexiones".', EmptyIcon: Users },
    { label: 'Coaches', items: state.coaches, Card: CoachCard, prop: 'coach', emptyTitle: 'No hay coaches aún', emptySubtitle: 'Los coaches asignados a esta organización aparecerán aquí.', EmptyIcon: UserCheck },
    ...(isOwner ? [{ label: 'Equipo', items: null, Card: null, prop: null, emptyTitle: '', emptySubtitle: '', EmptyIcon: null }] : []),
  ];

  const equipoTabIndex = standardTabs.findIndex((t) => t.label === 'Equipo');
  const activeTab = standardTabs[tab];

  return (
    <Box>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        {standardTabs.map((t) => (
          <Tab key={t.label} label={t.label} />
        ))}
      </Tabs>

      {/* Equipo tab */}
      {isOwner && tab === equipoTabIndex ? (
        <Box>
          {/* Action buttons */}
          <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
            <Button
              variant="contained"
              size="small"
              onClick={() => setInviteModal('coach')}
              sx={{
                bgcolor: '#1e293b', color: '#fff',
                '&:hover': { bgcolor: '#334155' },
                textTransform: 'none', fontWeight: 600,
              }}
            >
              + Invitar Coach
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setInviteModal('staff')}
              sx={{
                borderColor: '#8b5cf6', color: '#8b5cf6',
                '&:hover': { borderColor: '#7c3aed', bgcolor: 'rgba(139,92,246,0.05)' },
                textTransform: 'none', fontWeight: 600,
              }}
            >
              + Invitar Staff
            </Button>
          </Box>

          {/* Active team members */}
          {state.teamMembers.length > 0 && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Miembros activos
              </Typography>
              {state.teamMembers.map((m) => (
                <Box
                  key={m.id}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: 1.5,
                    py: 1.5, borderBottom: '1px solid rgba(0,0,0,0.06)',
                  }}
                >
                  <Avatar sx={{ width: 36, height: 36, bgcolor: ROLE_COLORS[m.role] || '#64748b', fontSize: 14, fontWeight: 700 }}>
                    {(m.name || '?')[0].toUpperCase()}
                  </Avatar>
                  <Box sx={{ flexGrow: 1 }}>
                    <Typography variant="body2" fontWeight={600}>{m.name}</Typography>
                    <Typography variant="caption" sx={{ color: '#64748b' }}>{m.email}</Typography>
                  </Box>
                  <Chip label={m.role} size="small" sx={{ bgcolor: `${ROLE_COLORS[m.role]}20`, color: ROLE_COLORS[m.role], fontWeight: 700, fontSize: '0.65rem' }} />
                  <Chip label="Activo" size="small" sx={{ bgcolor: '#dcfce7', color: '#16a34a', fontWeight: 700, fontSize: '0.65rem' }} />
                </Box>
              ))}
            </Box>
          )}

          {/* Pending invitations */}
          {state.pendingInvites.length > 0 && (
            <Box>
              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Invitaciones pendientes
              </Typography>
              {state.pendingInvites.map((inv) => (
                <Box
                  key={inv.id}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: 1.5,
                    py: 1.5, borderLeft: '3px solid #f59e0b', pl: 1.5,
                    borderBottom: '1px solid rgba(0,0,0,0.06)',
                    bgcolor: 'rgba(245,158,11,0.04)',
                  }}
                >
                  <Avatar sx={{ width: 36, height: 36, bgcolor: '#f59e0b', fontSize: 14, fontWeight: 700 }}>
                    ?
                  </Avatar>
                  <Box sx={{ flexGrow: 1 }}>
                    <Typography variant="body2" fontWeight={600} sx={{ color: '#92400e' }}>
                      {inv.email || 'Cualquier persona con el link'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748b', fontFamily: 'monospace' }}>
                      {String(inv.token).slice(0, 8)}…
                    </Typography>
                  </Box>
                  <Chip label={inv.role} size="small" sx={{ bgcolor: `${ROLE_COLORS[inv.role] || '#64748b'}20`, color: ROLE_COLORS[inv.role] || '#64748b', fontWeight: 700, fontSize: '0.65rem' }} />
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      const url = `${window.location.origin}/join/team/${inv.token}`;
                      navigator.clipboard?.writeText(url);
                    }}
                    sx={{ textTransform: 'none', fontSize: '0.7rem', borderColor: '#f59e0b', color: '#92400e', minWidth: 90 }}
                  >
                    Copiar link
                  </Button>
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => handleRevokeInvite(inv.id)}
                    sx={{ textTransform: 'none', fontSize: '0.7rem', color: '#ef4444', minWidth: 0, px: 1 }}
                    title="Revocar invitación"
                  >
                    ×
                  </Button>
                </Box>
              ))}
            </Box>
          )}

          {state.teamMembers.length === 0 && state.pendingInvites.length === 0 && (
            <Box sx={{ py: 8, textAlign: 'center' }}>
              <Users2 style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }} />
              <Typography variant="h6" fontWeight={600} sx={{ color: '#374151' }}>Sin miembros de equipo</Typography>
              <Typography variant="body2" sx={{ color: '#6b7280', mt: 0.5 }}>Invita coaches y staff para que colaboren en la organización.</Typography>
            </Box>
          )}
        </Box>
      ) : (
        /* Standard tab rendering */
        activeTab && activeTab.items !== null && (
          activeTab.items.length === 0 ? (
            <Box
              sx={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', py: 10, textAlign: 'center',
              }}
            >
              <activeTab.EmptyIcon style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }} />
              <Typography variant="h6" fontWeight={600} sx={{ color: '#374151' }}>
                {activeTab.emptyTitle}
              </Typography>
              <Typography variant="body2" sx={{ color: '#6b7280', mt: 0.5, maxWidth: 360 }}>
                {activeTab.emptySubtitle}
              </Typography>
            </Box>
          ) : (
            <Grid container spacing={2}>
              {activeTab.items.map((item) => (
                <Grid size={{ xs: 12, sm: 6, md: 4 }} key={item.id}>
                  <Box
                    onClick={activeTab.prop === 'athlete' && onSelectAthlete ? () => onSelectAthlete(item.id) : undefined}
                    sx={activeTab.prop === 'athlete' && onSelectAthlete ? { cursor: 'pointer' } : undefined}
                  >
                    <activeTab.Card {...{ [activeTab.prop]: item }} />
                  </Box>
                </Grid>
              ))}
            </Grid>
          )
        )
      )}

      {/* Invite team modal */}
      {inviteModal && (
        <InviteTeamModal
          open={!!inviteModal}
          defaultRole={inviteModal}
          orgId={orgId}
          onClose={() => setInviteModal(null)}
          onCreated={handleInviteCreated}
        />
      )}
    </Box>
  );
}
