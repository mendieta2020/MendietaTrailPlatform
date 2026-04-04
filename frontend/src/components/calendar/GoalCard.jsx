/**
 * GoalCard.jsx — Goal/race date card for calendar grid (PR-163)
 *
 * Props:
 *   goal    — { id, title, target_date, priority, status,
 *               target_distance_km, target_elevation_gain_m }
 *   onClick — (goal) => void
 */
import React from 'react';
import { Box, Typography } from '@mui/material';
import { parseISO, differenceInDays } from 'date-fns';

const PRIORITY_LABEL = { A: 'Principal', B: 'Secundario', C: 'Desarrollo' };
const PRIORITY_COLOR = { A: '#7c2d12', B: '#92400e', C: '#78350f' };

export default function GoalCard({ goal, onClick }) {
  const today = new Date();
  const targetDate = goal.target_date ? parseISO(goal.target_date) : null;
  const daysRemaining = targetDate ? differenceInDays(targetDate, today) : null;
  const isImminent = daysRemaining != null && daysRemaining <= 7 && daysRemaining >= 0;

  const subline = [
    goal.target_distance_km ? `${goal.target_distance_km}km` : null,
    goal.target_elevation_gain_m ? `D+${goal.target_elevation_gain_m}m` : null,
  ].filter(Boolean).join(' · ');

  return (
    <Box
      onClick={(e) => { e.stopPropagation(); onClick?.(goal); }}
      sx={{
        background: 'linear-gradient(135deg, #FFD700 0%, #F97316 100%)',
        borderRadius: '8px',
        px: 0.75,
        py: 0.5,
        mb: 0.5,
        cursor: 'pointer',
        '&:hover': { opacity: 0.88 },
        userSelect: 'none',
      }}
    >
      {isImminent && (
        <Typography sx={{ fontSize: '0.55rem', fontWeight: 800, color: '#7c2d12', lineHeight: 1.2, mb: 0.1 }}>
          🏆 Tu próximo desafío!
        </Typography>
      )}
      <Typography
        sx={{ fontSize: '0.65rem', fontWeight: 800, color: PRIORITY_COLOR[goal.priority] ?? '#7c2d12', lineHeight: 1.25, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
      >
        🏆 {goal.title}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.15 }}>
        {subline && (
          <Typography sx={{ fontSize: '0.55rem', color: '#92400e', lineHeight: 1.1 }}>
            {subline}
          </Typography>
        )}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {goal.priority && (
            <Box
              sx={{
                px: 0.4, py: 0,
                borderRadius: 0.5,
                bgcolor: 'rgba(0,0,0,0.12)',
                fontSize: '0.5rem',
                fontWeight: 700,
                color: '#7c2d12',
                lineHeight: 1.4,
              }}
            >
              {PRIORITY_LABEL[goal.priority] ?? goal.priority}
            </Box>
          )}
          {daysRemaining != null && daysRemaining >= 0 && (
            <Typography sx={{ fontSize: '0.5rem', color: '#92400e', fontWeight: 600 }}>
              {daysRemaining === 0 ? '¡Hoy!' : `${daysRemaining}d`}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
}
