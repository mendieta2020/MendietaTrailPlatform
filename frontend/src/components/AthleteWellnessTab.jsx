/**
 * AthleteWellnessTab — PR-159
 * Coach sees wellness heatmap + readiness trend for an athlete.
 */
import React, { useState, useEffect } from 'react'
import { Box, Typography, CircularProgress, Alert, Skeleton } from '@mui/material'
import WellnessHeatmap from './WellnessHeatmap'
import { getAthleteWellness } from '../api/pmc'

export default function AthleteWellnessTab({ membershipId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!membershipId) return
    getAthleteWellness(membershipId, 60)
      .then(res => { setData(res.data); setLoading(false) })
      .catch(() => { setError('No se pudo cargar el historial de bienestar.'); setLoading(false) })
  }, [membershipId])

  if (loading) return (
    <Box sx={{ space: 2 }}>
      <Skeleton variant="rectangular" height={200} sx={{ borderRadius: 2, mb: 2 }} />
    </Box>
  )
  if (error) return <Alert severity="error">{error}</Alert>

  const entries = data?.entries ?? []
  const avg = data?.period_average

  return (
    <Box>
      {avg !== null && avg !== undefined && (
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <Box sx={{
            bgcolor: 'white', border: '1px solid #e2e8f0', borderLeft: '4px solid #ec4899',
            borderRadius: 2, px: 2, py: 1.5,
          }}>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Bienestar promedio (60d)
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 700, color: '#ec4899', lineHeight: 1.1 }}>
              {avg.toFixed(1)}<span style={{ fontSize: '0.9rem', color: '#94a3b8' }}>/5</span>
            </Typography>
          </Box>
        </Box>
      )}

      {entries.length > 0 ? (
        <Box sx={{ bgcolor: 'white', border: '1px solid #e2e8f0', borderRadius: 2, p: 2 }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.7rem', display: 'block', mb: 1.5 }}>
            Heatmap de bienestar (últimos 60 días)
          </Typography>
          <WellnessHeatmap entries={entries} />
        </Box>
      ) : (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: '#94a3b8' }}>Sin check-ins de bienestar registrados</Typography>
        </Box>
      )}
    </Box>
  )
}
