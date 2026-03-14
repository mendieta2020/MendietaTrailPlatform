import React, { useReducer, useEffect } from 'react';
import { Tabs, Tab, Box, Grid, CircularProgress, Alert, Typography } from '@mui/material';
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

export default function RosterSection({ orgId }) {
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
    { label: 'Atletas', items: state.athletes, Card: AthleteCard, prop: 'athlete', empty: 'atletas' },
    { label: 'Coaches', items: state.coaches, Card: CoachCard, prop: 'coach', empty: 'coaches' },
    { label: 'Equipos', items: state.teams, Card: TeamCard, prop: 'team', empty: 'equipos' },
  ];

  const { items, Card, prop, empty } = tabs[tab];

  return (
    <Box>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        {tabs.map((t) => (
          <Tab key={t.label} label={t.label} />
        ))}
      </Tabs>

      {items.length === 0 ? (
        <Typography color="text.secondary">
          No hay {empty} en esta organización.
        </Typography>
      ) : (
        <Grid container spacing={2}>
          {items.map((item) => (
            <Grid item xs={12} sm={6} md={4} key={item.id}>
              <Card {...{ [prop]: item }} />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
