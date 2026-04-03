/**
 * AthleteWellnessTab — PR-160
 * Coach sees wellness heatmap + readiness trend + actionable interpretation text.
 */
import React, { useState, useEffect } from 'react'
import { Box, Typography, CircularProgress, Alert, Skeleton } from '@mui/material'
import WellnessHeatmap from './WellnessHeatmap'
import { getAthleteWellness } from '../api/pmc'

function computeAvg(entries, field, days = 7) {
  const recent = entries.slice(-days)
  if (recent.length === 0) return null
  const vals = recent.map(e => e[field]).filter(v => v != null)
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

function WellnessInterpretation({ entries, atl, ctl }) {
  if (!entries || entries.length < 3) return null

  const painAvg = computeAvg(entries, 'muscle_soreness', 7)
  const sleepAvg = computeAvg(entries, 'sleep_quality', 7)
  const energyAvg = computeAvg(entries, 'energy', 7)
  const moodAvg = computeAvg(entries, 'mood', 7)
  const stressAvg = computeAvg(entries, 'stress', 7)

  const alerts = []

  if (painAvg !== null && painAvg > 3.5) {
    alerts.push({ icon: '⚠️', color: '#d97706', text: 'Dolor muscular elevado — considerá reducir carga o revisar técnica' })
  }
  if (sleepAvg !== null && sleepAvg < 2.5) {
    alerts.push({ icon: '⚠️', color: '#d97706', text: 'Calidad de sueño baja — puede afectar la recuperación' })
  }
  if (energyAvg !== null && energyAvg < 2.5 && atl != null && ctl != null && atl > ctl) {
    alerts.push({ icon: '🔴', color: '#dc2626', text: 'Energía baja + carga alta — riesgo de sobreentrenamiento' })
  }
  if (stressAvg !== null && stressAvg > 3.5) {
    alerts.push({ icon: '⚠️', color: '#d97706', text: 'Estrés elevado — monitorear impacto en el rendimiento' })
  }

  const allGood =
    (painAvg == null || painAvg <= 3) &&
    (sleepAvg == null || sleepAvg >= 3) &&
    (energyAvg == null || energyAvg >= 3) &&
    (moodAvg == null || moodAvg >= 3) &&
    (stressAvg == null || stressAvg <= 3)

  if (alerts.length === 0 && allGood) {
    alerts.push({ icon: '✅', color: '#16a34a', text: 'Bienestar general bueno — el atleta responde bien al entrenamiento' })
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 2 }}>
      {alerts.map((a, i) => (
        <Box
          key={i}
          sx={{
            display: 'flex', alignItems: 'flex-start', gap: 1,
            bgcolor: 'white', border: '1px solid #e2e8f0', borderLeft: `4px solid ${a.color}`,
            borderRadius: 2, px: 1.5, py: 1,
          }}
        >
          <Typography sx={{ fontSize: '0.85rem', lineHeight: 1 }}>{a.icon}</Typography>
          <Typography variant="caption" sx={{ color: '#374151', fontSize: '0.75rem', lineHeight: 1.4 }}>
            {a.text}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

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
  // Latest PMC values if provided by the API
  const latestAtl = data?.latest_atl ?? null
  const latestCtl = data?.latest_ctl ?? null

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
        <>
          <Box sx={{ bgcolor: 'white', border: '1px solid #e2e8f0', borderRadius: 2, p: 2 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.7rem', display: 'block', mb: 1.5 }}>
              Heatmap de bienestar (últimos 60 días)
            </Typography>
            <WellnessHeatmap entries={entries} />
          </Box>

          {/* PR-160: Interpretation text */}
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: '0.7rem', display: 'block', mb: 0.5 }}>
              Análisis últimos 7 días
            </Typography>
            <WellnessInterpretation entries={entries} atl={latestAtl} ctl={latestCtl} />
          </Box>
        </>
      ) : (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: '#94a3b8' }}>Sin check-ins de bienestar registrados</Typography>
        </Box>
      )}
    </Box>
  )
}
