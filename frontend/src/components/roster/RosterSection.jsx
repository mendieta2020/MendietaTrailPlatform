import React, { useReducer, useEffect } from 'react';
import { Tabs, Tab, Box, Grid, CircularProgress, Alert, Typography } from '@mui/material';
import { Users, UserCheck, Users2 } from 'lucide-react';
import { listAthletes, listCoaches, listTeams } from '../../api/p1';
import AthleteCard from './AthleteCard';
import CoachCard from './CoachCard';
import TeamCard from './TeamCard';

const initialState = {
  loading: false,
  error: null,
  athletes: [],
  coaches: [],
  teams: [],
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
        teams: action.teams,
      };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export default function RosterSection({ orgId, onSelectAthlete }) {
  const [tab, setTab] = React.useState(0);
  const [state, dispatch] = useReducer(rosterReducer, initialState);

  useEffect(() => {
    if (!orgId) return;
    dispatch({ type: 'FETCH_START' });

    Promise.all([listAthletes(orgId), listCoaches(orgId), listTeams(orgId)])
      .then(([athletesRes, coachesRes, teamsRes]) => {
        dispatch({
          type: 'FETCH_SUCCESS',
          athletes: athletesRes.data?.results ?? athletesRes.data ?? [],
          coaches: coachesRes.data?.results ?? coachesRes.data ?? [],
          teams: teamsRes.data?.results ?? teamsRes.data ?? [],
        });
      })
      .catch(() =>
        dispatch({
          type: 'FETCH_ERROR',
          error: 'No se pudo cargar el roster. Intenta de nuevo.',
        })
      );
  }, [orgId]);

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

  const tabs = [
    { label: 'Atletas', items: state.athletes, Card: AthleteCard, prop: 'athlete', emptyTitle: 'No hay atletas aún', emptySubtitle: 'Agrega atletas a la organización usando "Gestionar Conexiones".', EmptyIcon: Users },
    { label: 'Coaches', items: state.coaches, Card: CoachCard, prop: 'coach', emptyTitle: 'No hay coaches aún', emptySubtitle: 'Los coaches asignados a esta organización aparecerán aquí.', EmptyIcon: UserCheck },
    { label: 'Equipos', items: state.teams, Card: TeamCard, prop: 'team', emptyTitle: 'No hay equipos aún', emptySubtitle: 'Crea equipos para organizar a tus atletas por grupos de entrenamiento.', EmptyIcon: Users2 },
  ];

  const { items, Card, prop, emptyTitle, emptySubtitle, EmptyIcon } = tabs[tab];

  return (
    <Box>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        {tabs.map((t) => (
          <Tab key={t.label} label={t.label} />
        ))}
      </Tabs>

      {items.length === 0 ? (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 10,
            textAlign: 'center',
          }}
        >
          <EmptyIcon style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }} />
          <Typography variant="h6" fontWeight={600} sx={{ color: '#374151' }}>
            {emptyTitle}
          </Typography>
          <Typography variant="body2" sx={{ color: '#6b7280', mt: 0.5, maxWidth: 360 }}>
            {emptySubtitle}
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {items.map((item) => (
            <Grid item xs={12} sm={6} md={4} key={item.id}>
              <Box
                onClick={prop === 'athlete' && onSelectAthlete ? () => onSelectAthlete(item.id) : undefined}
                sx={prop === 'athlete' && onSelectAthlete ? { cursor: 'pointer' } : undefined}
              >
                <Card {...{ [prop]: item }} />
              </Box>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
