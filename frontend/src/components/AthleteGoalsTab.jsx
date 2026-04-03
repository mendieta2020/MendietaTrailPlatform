/**
 * AthleteGoalsTab — PR-159
 * Coach sees athlete race goals with days remaining, priority, distance, elevation.
 */
import React, { useState, useEffect } from 'react'
import { Box, Typography, CircularProgress, Alert, Chip } from '@mui/material'
import { getCoachAthleteGoals } from '../api/pmc'

const PRIORITY_COLORS = {
  A: { bg: 'rgba(245,124,0,0.12)', color: '#F57C00', label: 'A — Principal' },
  B: { bg: 'rgba(59,130,246,0.1)', color: '#2563eb', label: 'B — Secundario' },
  C: { bg: 'rgba(100,116,139,0.1)', color: '#64748b', label: 'C — Desarrollo' },
}

const STATUS_COLORS = {
  active: { bg: 'rgba(34,197,94,0.1)', color: '#16a34a' },
  planned: { bg: 'rgba(148,163,184,0.15)', color: '#64748b' },
  completed: { bg: 'rgba(59,130,246,0.1)', color: '#2563eb' },
  paused: { bg: 'rgba(234,179,8,0.1)', color: '#ca8a04' },
  cancelled: { bg: '#f8fafc', color: '#94a3b8' },
}

export default function AthleteGoalsTab({ membershipId }) {
  const [goals, setGoals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!membershipId) return
    getCoachAthleteGoals(membershipId)
      .then(res => { setGoals(res.data.results ?? []); setLoading(false) })
      .catch(() => { setError('No se pudieron cargar los objetivos.'); setLoading(false) })
  }, [membershipId])

  if (loading) return <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>
  if (error) return <Alert severity="error">{error}</Alert>

  if (goals.length === 0) {
    return (
      <Box sx={{ py: 6, textAlign: 'center' }}>
        <Typography variant="body2" sx={{ color: '#94a3b8' }}>Sin objetivos registrados</Typography>
      </Box>
    )
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {goals.map(goal => {
        const prio = PRIORITY_COLORS[goal.priority] ?? PRIORITY_COLORS.C
        const stat = STATUS_COLORS[goal.status] ?? STATUS_COLORS.planned
        const isUpcoming = goal.days_remaining !== null && goal.days_remaining >= 0
        const isUrgent = goal.days_remaining !== null && goal.days_remaining <= 7 && isUpcoming

        return (
          <Box
            key={goal.id}
            sx={{
              bgcolor: 'white',
              border: '1px solid #e2e8f0',
              borderLeft: `4px solid ${prio.color}`,
              borderRadius: 2,
              p: 2,
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 1 }}>
              <Box>
                <Typography variant="body1" sx={{ fontWeight: 700, color: '#0f172a', mb: 0.5 }}>
                  {goal.title}
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Chip
                    label={prio.label}
                    size="small"
                    sx={{ height: 18, fontSize: '0.65rem', bgcolor: prio.bg, color: prio.color, fontWeight: 700 }}
                  />
                  <Chip
                    label={goal.status}
                    size="small"
                    sx={{ height: 18, fontSize: '0.65rem', bgcolor: stat.bg, color: stat.color }}
                  />
                </Box>
              </Box>

              {goal.target_date && (
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="caption" sx={{ color: '#64748b', display: 'block' }}>
                    {goal.target_date}
                  </Typography>
                  {goal.days_remaining !== null && (
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        color: isUrgent ? '#dc2626' : isUpcoming ? '#F57C00' : '#94a3b8',
                      }}
                    >
                      {goal.days_remaining === 0
                        ? 'Hoy'
                        : goal.days_remaining > 0
                          ? `En ${goal.days_remaining} días`
                          : `Hace ${Math.abs(goal.days_remaining)} días`}
                    </Typography>
                  )}
                </Box>
              )}
            </Box>

            {(goal.target_distance_km || goal.target_elevation_gain_m) && (
              <Box sx={{ display: 'flex', gap: 2, mt: 1.5, pt: 1.5, borderTop: '1px solid #f1f5f9' }}>
                {goal.target_distance_km && (
                  <Box>
                    <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.7rem', display: 'block' }}>Distancia</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b' }}>{goal.target_distance_km} km</Typography>
                  </Box>
                )}
                {goal.target_elevation_gain_m && (
                  <Box>
                    <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.7rem', display: 'block' }}>Desnivel +</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b' }}>{goal.target_elevation_gain_m} m</Typography>
                  </Box>
                )}
              </Box>
            )}

            {goal.coach_notes && (
              <Typography variant="caption" sx={{ display: 'block', mt: 1, color: '#64748b', fontStyle: 'italic' }}>
                {goal.coach_notes}
              </Typography>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
