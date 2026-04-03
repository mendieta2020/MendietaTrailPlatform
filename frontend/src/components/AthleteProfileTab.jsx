/**
 * AthleteProfileTab — PR-159 / PR-161
 * Coach reads and edits athlete personal, physical, and availability data.
 * PR-161: Datos Personales and Disponibilidad Semanal are now editable.
 */
import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Button, TextField, Checkbox, CircularProgress, Alert, Grid,
} from '@mui/material'
import { getCoachAthleteProfile, patchCoachAthleteProfile } from '../api/pmc'
import { updateAvailability } from '../api/athlete'
import { useOrg } from '../context/OrgContext'

const DAY_LABELS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

function Section({ title, children, onEdit, editing, onSave, onCancel, saving }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1e293b', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {title}
        </Typography>
        {!editing && onEdit && (
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
  const { org } = useOrg()
  const orgId = org?.id

  const [data,          setData]          = useState(null)
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState(null)

  // ── Personal section ─────────────────────────────────────────────────────
  const [editPersonal,   setEditPersonal]   = useState(false)
  const [personalDraft,  setPersonalDraft]  = useState({})
  const [savingPersonal, setSavingPersonal] = useState(false)

  // ── Physical section ─────────────────────────────────────────────────────
  const [editPhysical,   setEditPhysical]   = useState(false)
  const [physicalDraft,  setPhysicalDraft]  = useState({})
  const [savingPhysical, setSavingPhysical] = useState(false)

  // ── Availability section ─────────────────────────────────────────────────
  const [editAvail,   setEditAvail]   = useState(false)
  const [availDraft,  setAvailDraft]  = useState([])
  const [savingAvail, setSavingAvail] = useState(false)

  useEffect(() => {
    if (!membershipId) return
    setLoading(true)
    getCoachAthleteProfile(membershipId)
      .then(res => { setData(res.data); setLoading(false) })
      .catch(() => { setError('No se pudo cargar el perfil del atleta.'); setLoading(false) })
  }, [membershipId])

  const profile      = data?.profile ?? {}
  const availability = data?.availability ?? []
  const athleteId    = data?.athlete_id

  // ── Personal handlers ────────────────────────────────────────────────────

  const startEditPersonal = () => {
    setPersonalDraft({
      birth_date:              profile.birth_date ?? '',
      emergency_contact_name:  profile.emergency_contact_name ?? '',
      emergency_contact_phone: profile.emergency_contact_phone ?? '',
      instagram_handle:        profile.instagram_handle ?? '',
    })
    setEditPersonal(true)
  }

  const savePersonal = async () => {
    setSavingPersonal(true)
    try {
      const cleaned = {}
      Object.entries(personalDraft).forEach(([k, v]) => {
        cleaned[k] = v === '' ? null : v
      })
      const res = await patchCoachAthleteProfile(membershipId, cleaned)
      setData(prev => ({ ...prev, profile: { ...prev.profile, ...res.data } }))
      setEditPersonal(false)
    } catch {
      setError('Error al guardar. Intenta de nuevo.')
    } finally {
      setSavingPersonal(false)
    }
  }

  // ── Physical handlers ────────────────────────────────────────────────────

  const startEditPhysical = () => {
    setPhysicalDraft({
      weight_kg:              profile.weight_kg ?? '',
      height_cm:              profile.height_cm ?? '',
      max_hr_bpm:             profile.max_hr_bpm ?? '',
      resting_hr_bpm:         profile.resting_hr_bpm ?? '',
      vo2max:                 profile.vo2max ?? '',
      training_age_years:     profile.training_age_years ?? '',
      weekly_available_hours: profile.weekly_available_hours ?? '',
      preferred_training_time: profile.preferred_training_time ?? '',
      pace_1000m_seconds:     profile.pace_1000m_seconds ?? '',
    })
    setEditPhysical(true)
  }

  const savePhysical = async () => {
    setSavingPhysical(true)
    const TEXT_FIELDS = new Set(['preferred_training_time'])
    try {
      const cleaned = {}
      Object.entries(physicalDraft).forEach(([k, v]) => {
        cleaned[k] = v === '' ? null : TEXT_FIELDS.has(k) ? v : Number(v)
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

  // ── Availability handlers ────────────────────────────────────────────────

  const startEditAvail = () => {
    // Build draft: 7 days (0=Mon…6=Sun), default to current state
    const draft = DAY_LABELS.map((_, i) => {
      const existing = availability.find(a => a.day_of_week === i + 1)
      return {
        day_of_week:  i + 1,
        is_available: existing?.is_available ?? true,
        reason:       existing?.reason ?? '',
        preferred_time: existing?.preferred_time ?? '',
      }
    })
    setAvailDraft(draft)
    setEditAvail(true)
  }

  const toggleDay = (idx) => {
    setAvailDraft(prev => prev.map((d, i) =>
      i === idx ? { ...d, is_available: !d.is_available } : d
    ))
  }

  const saveAvail = async () => {
    if (!orgId || !athleteId) { setError('No se pudo determinar la organización.'); return }
    setSavingAvail(true)
    try {
      const { data: saved } = await updateAvailability(orgId, athleteId, availDraft)
      setData(prev => ({
        ...prev,
        availability: Array.isArray(saved) ? saved : saved?.results ?? [],
      }))
      setEditAvail(false)
    } catch {
      setError('Error al guardar disponibilidad.')
    } finally {
      setSavingAvail(false)
    }
  }

  // ────────────────────────────────────────────────────────────────────────

  if (loading) return <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>
  if (error)   return <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>

  const fullName = data?.athlete_name ?? '—'
  const email    = data?.athlete_email ?? '—'

  return (
    <Box>
      {/* ── Personal (now editable) ──────────────────────────────────────── */}
      <Section
        title="Datos Personales"
        editing={editPersonal}
        onEdit={startEditPersonal}
        onSave={savePersonal}
        onCancel={() => setEditPersonal(false)}
        saving={savingPersonal}
      >
        {editPersonal ? (
          <Grid container spacing={2}>
            {/* Name + Email are read-only (User model fields) */}
            <Grid item xs={12} sm={6}><ReadField label="Nombre" value={fullName} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Email" value={email} /></Grid>
            {[
              { key: 'birth_date',              label: 'Fecha de nacimiento', type: 'date' },
              { key: 'emergency_contact_name',  label: 'Contacto emergencia', type: 'text' },
              { key: 'emergency_contact_phone', label: 'Tel. emergencia',     type: 'text' },
              { key: 'instagram_handle',        label: 'Instagram',           type: 'text' },
            ].map(({ key, label, type }) => (
              <Grid item xs={12} sm={6} key={key}>
                <TextField
                  label={label}
                  type={type}
                  size="small"
                  fullWidth
                  value={personalDraft[key] ?? ''}
                  onChange={e => setPersonalDraft(d => ({ ...d, [key]: e.target.value }))}
                  InputLabelProps={type === 'date' ? { shrink: true } : undefined}
                />
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}><ReadField label="Nombre" value={fullName} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Email" value={email} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Fecha de nacimiento" value={profile.birth_date} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Contacto de emergencia" value={profile.emergency_contact_name} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Tel. emergencia" value={profile.emergency_contact_phone} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Instagram" value={profile.instagram_handle ? `@${profile.instagram_handle}` : null} /></Grid>
          </Grid>
        )}
      </Section>

      {/* ── Physical (already editable) ──────────────────────────────────── */}
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
              { key: 'weight_kg',              label: 'Peso (kg)',          type: 'number' },
              { key: 'height_cm',              label: 'Altura (cm)',        type: 'number' },
              { key: 'max_hr_bpm',             label: 'FC Máx (bpm)',       type: 'number' },
              { key: 'resting_hr_bpm',         label: 'FC Reposo (bpm)',    type: 'number' },
              { key: 'vo2max',                 label: 'VO2max',             type: 'number' },
              { key: 'training_age_years',     label: 'Años entrenando',    type: 'number' },
              { key: 'weekly_available_hours', label: 'Horas/semana',       type: 'number' },
              { key: 'preferred_training_time', label: 'Horario preferido', type: 'text' },
              { key: 'pace_1000m_seconds',     label: 'Ritmo 1km (seg)',    type: 'number' },
            ].map(({ key, label, type }) => (
              <Grid item xs={12} sm={6} key={key}>
                <TextField
                  label={label}
                  type={type}
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
            <Grid item xs={12} sm={6}><ReadField label="Horas/semana" value={profile.weekly_available_hours} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Horario preferido" value={profile.preferred_training_time} /></Grid>
            <Grid item xs={12} sm={6}><ReadField label="Ritmo 1km" value={profile.pace_1000m_seconds ? `${profile.pace_1000m_seconds}s` : null} /></Grid>
          </Grid>
        )}
      </Section>

      {/* ── Availability (now editable) ───────────────────────────────────── */}
      <Section
        title="Disponibilidad Semanal"
        editing={editAvail}
        onEdit={startEditAvail}
        onSave={saveAvail}
        onCancel={() => setEditAvail(false)}
        saving={savingAvail}
      >
        {editAvail ? (
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {availDraft.map((day, i) => (
              <Box
                key={DAY_LABELS[i]}
                onClick={() => toggleDay(i)}
                sx={{
                  px: 1.5, py: 1, borderRadius: 1.5, cursor: 'pointer',
                  bgcolor: day.is_available ? 'rgba(34,197,94,0.1)' : '#f8fafc',
                  border: `2px solid ${day.is_available ? '#22c55e' : '#e2e8f0'}`,
                  minWidth: 80, textAlign: 'center',
                  transition: 'all 0.15s',
                  '&:hover': { borderColor: day.is_available ? '#16a34a' : '#F57C00' },
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 700, color: day.is_available ? '#16a34a' : '#94a3b8', fontSize: '0.75rem', display: 'block' }}>
                  {DAY_LABELS[i].slice(0, 3)}
                </Typography>
                <Typography variant="caption" sx={{ color: day.is_available ? '#22c55e' : '#cbd5e1', fontSize: '0.65rem' }}>
                  {day.is_available ? '✓ Disponible' : '✗ No'}
                </Typography>
              </Box>
            ))}
          </Box>
        ) : (
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
        )}
      </Section>
    </Box>
  )
}
