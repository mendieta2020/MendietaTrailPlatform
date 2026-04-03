/**
 * AthleteProfileTab — PR-159
 * Coach reads and edits athlete personal, physical, and availability data.
 */
import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Button, TextField, Checkbox, FormControlLabel,
  CircularProgress, Alert, Divider, Grid
} from '@mui/material'
import { getCoachAthleteProfile, patchCoachAthleteProfile } from '../api/pmc'

const DAY_LABELS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

function Section({ title, children, onEdit, editing, onSave, onCancel, saving }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1e293b', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {title}
        </Typography>
        {!editing && (
          <Button size="small" onClick={onEdit} sx={{ color: '#F57C00', fontSize: '0.75rem' }}>
            Editar
          </Button>
        )}
        {editing && (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" onClick={onCancel} sx={{ color: '#64748b', fontSize: '0.75rem' }}>
              Cancelar
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={onSave}
              disabled={saving}
              sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' }, fontSize: '0.75rem' }}
            >
              {saving ? <CircularProgress size={12} sx={{ color: '#fff' }} /> : 'Guardar'}
            </Button>
          </Box>
        )}
      </Box>
      <Box sx={{ bgcolor: 'white', borderRadius: 2, border: '1px solid #e2e8f0', p: 2 }}>
        {children}
      </Box>
    </Box>
  )
}

function ReadField({ label, value }) {
  return (
    <Box>
      <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ color: '#1e293b', fontWeight: 500, mt: 0.25 }}>
        {value || '—'}
      </Typography>
    </Box>
  )
}

export default function AthleteProfileTab({ membershipId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Edit sections
  const [editPhysical, setEditPhysical] = useState(false)
  const [physicalDraft, setPhysicalDraft] = useState({})
  const [savingPhysical, setSavingPhysical] = useState(false)

  useEffect(() => {
    if (!membershipId) return
    setLoading(true)
    getCoachAthleteProfile(membershipId)
      .then(res => {
        setData(res.data)
        setLoading(false)
      })
      .catch(() => {
        setError('No se pudo cargar el perfil del atleta.')
        setLoading(false)
      })
  }, [membershipId])

  const profile = data?.profile ?? {}
  const availability = data?.availability ?? []

  // Physical section handlers
  const startEditPhysical = () => {
    setPhysicalDraft({
      weight_kg: profile.weight_kg ?? '',
      height_cm: profile.height_cm ?? '',
      max_hr_bpm: profile.max_hr_bpm ?? '',
      resting_hr_bpm: profile.resting_hr_bpm ?? '',
      vo2max: profile.vo2max ?? '',
      training_age_years: profile.training_age_years ?? '',
    })
    setEditPhysical(true)
  }

  const savePhysical = async () => {
    setSavingPhysical(true)
    try {
      const cleaned = {}
      Object.entries(physicalDraft).forEach(([k, v]) => {
        cleaned[k] = v === '' ? null : Number(v)
      })
      const res = await patchCoachAthleteProfile(membershipId, cleaned)
      setData(prev => ({ ...prev, profile: { ...prev.profile, ...res.data } }))
      setEditPhysical(false)
    } catch {
      setError('Error al guardar. Intenta de nuevo.')
    } finally {
      setSavingPhysical(false)
    }
  }

  if (loading) return <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>
  if (error) return <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>

  const fullName = data?.athlete_name ?? '—'
  const email = data?.athlete_email ?? '—'

  return (
    <Box>
      {/* Personal info (read-only) */}
      <Section title="Datos Personales">
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}><ReadField label="Nombre" value={fullName} /></Grid>
          <Grid item xs={12} sm={6}><ReadField label="Email" value={email} /></Grid>
          <Grid item xs={12} sm={6}><ReadField label="Fecha de nacimiento" value={profile.birth_date} /></Grid>
          <Grid item xs={12} sm={6}><ReadField label="Contacto de emergencia" value={profile.emergency_contact_name} /></Grid>
          <Grid item xs={12} sm={6}><ReadField label="Tel. emergencia" value={profile.emergency_contact_phone} /></Grid>
          <Grid item xs={12} sm={6}><ReadField label="Instagram" value={profile.instagram_handle ? `@${profile.instagram_handle}` : null} /></Grid>
        </Grid>
      </Section>

      {/* Physical data (editable) */}
      <Section
        title="Datos Físicos"
        editing={editPhysical}
        onEdit={startEditPhysical}
        onSave={savePhysical}
        onCancel={() => setEditPhysical(false)}
        saving={savingPhysical}
      >
        {editPhysical ? (
          <Grid container spacing={2}>
            {[
              { key: 'weight_kg', label: 'Peso (kg)' },
              { key: 'height_cm', label: 'Altura (cm)' },
              { key: 'max_hr_bpm', label: 'FC Máx (bpm)' },
              { key: 'resting_hr_bpm', label: 'FC Reposo (bpm)' },
              { key: 'vo2max', label: 'VO2max' },
              { key: 'training_age_years', label: 'Años entrenando' },
            ].map(({ key, label }) => (
              <Grid item xs={12} sm={6} key={key}>
                <TextField
                  label={label}
                  type="number"
                  size="small"
                  fullWidth
                  value={physicalDraft[key] ?? ''}
                  onChange={e => setPhysicalDraft(d => ({ ...d, [key]: e.target.value }))}
                />
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}><ReadField label="Peso" value={profile.weight_kg ? `${profile.weight_kg} kg` : null} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Altura" value={profile.height_cm ? `${profile.height_cm} cm` : null} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="FC Máx" value={profile.max_hr_bpm ? `${profile.max_hr_bpm} bpm` : null} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="FC Reposo" value={profile.resting_hr_bpm ? `${profile.resting_hr_bpm} bpm` : null} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="VO2max" value={profile.vo2max} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Años entrenando" value={profile.training_age_years} /></Grid>
          </Grid>
        )}
      </Section>

      {/* Availability (read-only for now) */}
      <Section title="Disponibilidad Semanal">
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {DAY_LABELS.map((day, i) => {
            const avail = availability.find(a => a.day_of_week === i + 1)
            const available = avail?.is_available ?? false
            return (
              <Box
                key={day}
                sx={{
                  px: 1.5, py: 0.75, borderRadius: 1.5,
                  bgcolor: available ? 'rgba(34,197,94,0.1)' : '#f8fafc',
                  border: `1px solid ${available ? '#22c55e' : '#e2e8f0'}`,
                  minWidth: 80, textAlign: 'center',
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 600, color: available ? '#16a34a' : '#94a3b8', fontSize: '0.72rem' }}>
                  {day.slice(0, 3)}
                </Typography>
                <Typography variant="caption" sx={{ display: 'block', color: available ? '#16a34a' : '#cbd5e1', fontSize: '0.67rem' }}>
                  {available ? 'Disponible' : 'No'}
                </Typography>
              </Box>
            )
          })}
        </Box>
      </Section>
    </Box>
  )
}
