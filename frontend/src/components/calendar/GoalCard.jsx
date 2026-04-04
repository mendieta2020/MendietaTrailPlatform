/**
 * GoalCard.jsx — Goal/race date card for calendar grid (PR-163)
 *
 * Props:
 *   goal    — { id, title, target_date, priority, status,
 *               target_distance_km, target_elevation_gain_m }
 *   onClick — (goal) => void
 */
import React from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { parseISO, differenceInDays } from 'date-fns';

const PRIORITY_LABEL = { A: 'Prioridad A — Principal', B: 'Prioridad B — Secundario', C: 'Prioridad C — Desarrollo' };

export default function GoalCard({ goal, onClick }) {
  const today = new Date();
  const targetDate = goal.target_date ? parseISO(goal.target_date) : null;
  const daysRemaining = targetDate ? differenceInDays(targetDate, today) : null;
  const isImminent = daysRemaining != null && daysRemaining <= 7 && daysRemaining >= 0;

  const subline = [
    goal.target_distance_km ? `${goal.target_distance_km}km` : null,
    goal.target_elevation_gain_m ? `D+${goal.target_elevation_gain_m}m` : null,
    goal.target_date ? goal.target_date : null,
  ].filter(Boolean).join(' · ');

  return (
    <Paper
      component={Box}
      onClick={(e) => { e.stopPropagation(); onClick?.(goal); }}
      sx={{
        bgcolor: '#FFF8E1',
        borderRadius: 2,
        boxShadow: 'none',
        border: '1px solid #e2e8f0',
        borderLeftColor: '#FFB300',
        borderLeftWidth: 3,
        borderLeftStyle: 'solid',
        px: 0.75,
        py: 0.5,
        mb: 0.5,
        minHeight: 72,
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        '&:hover': { boxShadow: '0 2px 8px rgba(255,179,0,0.18)', bgcolor: '#FFF3CD' },
        userSelect: 'none',
      }}
    >
      {/* Row 1: Trophy + priority + today badge */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: '#92400e', letterSpacing: 0.3, textTransform: 'uppercase' }}>
          🏆 {goal.priority ?? 'B'}
        </Typography>
        {daysRemaining === 0 && (
          <Box sx={{ px: 0.5, py: 0.05, borderRadius: 0.75, bgcolor: '#f97316', fontSize: '0.5rem', fontWeight: 700, color: '#fff' }}>
            ¡Hoy!
          </Box>
        )}
      </Box>

      {/* Row 2: Race name */}
      <Typography
        sx={{ fontWeight: 700, color: '#78350f', fontSize: '0.72rem', lineHeight: 1.25, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', mt: 0.15 }}
      >
        {goal.title}
      </Typography>

      {/* Row 3: Distance · D+ · Date */}
      {subline && (
        <Typography sx={{ fontSize: '0.55rem', color: '#92400e', lineHeight: 1.1, mt: 0.15 }}>
          {subline}
        </Typography>
      )}

      {/* Row 4: Priority chip */}
      <Box sx={{ mt: 0.25 }}>
        <Box
          sx={{
            display: 'inline-block',
            px: 0.5, py: 0.05,
            borderRadius: 0.75,
            bgcolor: 'rgba(146,64,14,0.1)',
            fontSize: '0.5rem',
            fontWeight: 700,
            color: '#92400e',
            lineHeight: 1.4,
          }}
        >
          {PRIORITY_LABEL[goal.priority] ?? goal.priority}
        </Box>
      </Box>

      {/* Row 5: Imminent countdown */}
      {isImminent && daysRemaining > 0 && (
        <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: '#dc2626', mt: 0.25 }}>
          🔥 Faltan {daysRemaining} días
        </Typography>
      )}
    </Paper>
  );
}
