/**
 * AthleteInjuriesTab — PR-159
 * Coach sees injury list + can add a new injury.
 */
import React, { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Button, TextField, MenuItem, Select, FormControl,
  InputLabel, CircularProgress, Alert, Chip, Divider
} from '@mui/material'
import { getCoachAthleteInjuries, createCoachAthleteInjury } from '../api/pmc'

const INJURY_TYPES = [
  { value: 'muscular', label: 'Muscular' },
  { value: 'articular', label: 'Articular' },
  { value: 'tendinosa', label: 'Tendinosa' },
  { value: 'ligamentosa', label: 'Ligamentosa' },
  { value: 'osea', label: 'Ósea' },
  { value: 'otra', label: 'Otra' },
]

const BODY_ZONES = [
  { value: 'cabeza', label: 'Cabeza' }, { value: 'cuello', label: 'Cuello' },
  { value: 'hombro', label: 'Hombro' }, { value: 'brazo', label: 'Brazo' },
  { value: 'codo', label: 'Codo' }, { value: 'muneca', label: 'Muñeca' },
  { value: 'mano', label: 'Mano' }, { value: 'pecho', label: 'Pecho' },
  { value: 'espalda_alta', label: 'Espalda Alta' }, { value: 'espalda_baja', label: 'Espalda Baja' },
  { value: 'cadera', label: 'Cadera' }, { value: 'muslo', label: 'Muslo' },
  { value: 'rodilla', label: 'Rodilla' }, { value: 'pantorrilla', label: 'Pantorrilla' },
  { value: 'espinilla', label: 'Espinilla' }, { value: 'tobillo', label: 'Tobillo' },
  { value: 'pie', label: 'Pie' }, { value: 'gluteo', label: 'Glúteo' },
  { value: 'isquiotibial', label: 'Isquiotibial' }, { value: 'talon', label: 'Talón' },
  { value: 'planta_del_pie', label: 'Planta del pie' },
]

const SEVERITIES = [
  { value: 'leve', label: 'Leve' },
  { value: 'moderada', label: 'Moderada' },
  { value: 'severa', label: 'Severa' },
]

const STATUSES = [
  { value: 'activa', label: 'Activa' },
  { value: 'en_recuperacion', label: 'En recuperación' },
  { value: 'resuelta', label: 'Resuelta' },
]

const STATUS_COLORS = {
  activa: { bg: 'rgba(239,68,68,0.1)', color: '#dc2626' },
  en_recuperacion: { bg: 'rgba(234,179,8,0.1)', color: '#ca8a04' },
  resuelta: { bg: 'rgba(34,197,94,0.1)', color: '#16a34a' },
}

export default function AthleteInjuriesTab({ membershipId }) {
  const [injuries, setInjuries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    injury_type: 'muscular',
    body_zone: 'rodilla',
    severity: 'leve',
    status: 'activa',
    date_occurred: new Date().toISOString().slice(0, 10),
    description: '',
  })

  const load = useCallback(() => {
    if (!membershipId) return
    setLoading(true)
    getCoachAthleteInjuries(membershipId)
      .then(res => { setInjuries(res.data.results ?? []); setLoading(false) })
      .catch(() => { setError('No se pudo cargar el historial de lesiones.'); setLoading(false) })
  }, [membershipId])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    setSaving(true)
    try {
      await createCoachAthleteInjury(membershipId, form)
      setShowForm(false)
      setForm({ injury_type: 'muscular', body_zone: 'rodilla', severity: 'leve', status: 'activa', date_occurred: new Date().toISOString().slice(0, 10), description: '' })
      load()
    } catch {
      setError('Error al guardar la lesión.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>

  return (
    <Box>
      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>}

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1e293b' }}>
          Historial de lesiones ({injuries.length})
        </Typography>
        <Button
          size="small"
          variant="outlined"
          onClick={() => setShowForm(!showForm)}
          sx={{ borderColor: '#F57C00', color: '#F57C00', fontSize: '0.75rem' }}
        >
          {showForm ? 'Cancelar' : '+ Agregar lesión'}
        </Button>
      </Box>

      {/* Add injury form */}
      {showForm && (
        <Box sx={{ bgcolor: 'white', border: '1px solid #e2e8f0', borderRadius: 2, p: 2, mb: 2 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1.5, color: '#1e293b' }}>Nueva lesión</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1.5 }}>
            <FormControl size="small" fullWidth>
              <InputLabel>Tipo</InputLabel>
              <Select value={form.injury_type} label="Tipo" onChange={e => setForm(f => ({ ...f, injury_type: e.target.value }))}>
                {INJURY_TYPES.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>Zona</InputLabel>
              <Select value={form.body_zone} label="Zona" onChange={e => setForm(f => ({ ...f, body_zone: e.target.value }))}>
                {BODY_ZONES.map(z => <MenuItem key={z.value} value={z.value}>{z.label}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>Severidad</InputLabel>
              <Select value={form.severity} label="Severidad" onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                {SEVERITIES.map(s => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>Estado</InputLabel>
              <Select value={form.status} label="Estado" onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                {STATUSES.map(s => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField
              label="Fecha"
              type="date"
              size="small"
              value={form.date_occurred}
              onChange={e => setForm(f => ({ ...f, date_occurred: e.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
          </Box>
          <TextField
            label="Descripción"
            multiline
            rows={2}
            size="small"
            fullWidth
            sx={{ mt: 1.5 }}
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          />
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1.5 }}>
            <Button
              size="small"
              variant="contained"
              onClick={handleSave}
              disabled={saving}
              sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
            >
              {saving ? <CircularProgress size={12} sx={{ color: '#fff' }} /> : 'Guardar'}
            </Button>
          </Box>
        </Box>
      )}

      {/* Injury list */}
      {injuries.length === 0 ? (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: '#94a3b8' }}>Sin lesiones registradas</Typography>
        </Box>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {injuries.map(inj => {
            const col = STATUS_COLORS[inj.status] ?? STATUS_COLORS.activa
            return (
              <Box
                key={inj.id}
                sx={{ bgcolor: 'white', border: '1px solid #e2e8f0', borderRadius: 2, p: 2, display: 'flex', gap: 2, alignItems: 'flex-start' }}
              >
                <Box sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b' }}>
                      {BODY_ZONES.find(z => z.value === inj.body_zone)?.label ?? inj.body_zone}
                    </Typography>
                    <Chip
                      label={inj.injury_type}
                      size="small"
                      sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#f1f5f9', color: '#475569' }}
                    />
                    <Chip
                      label={inj.severity}
                      size="small"
                      sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#fef3c7', color: '#92400e' }}
                    />
                  </Box>
                  {inj.description && (
                    <Typography variant="caption" sx={{ color: '#64748b', display: 'block', mt: 0.5 }}>
                      {inj.description}
                    </Typography>
                  )}
                  <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
                    {inj.date_occurred}
                    {inj.resolved_at && ` → ${inj.resolved_at}`}
                  </Typography>
                </Box>
                <Chip
                  label={STATUSES.find(s => s.value === inj.status)?.label ?? inj.status}
                  size="small"
                  sx={{ height: 20, fontSize: '0.67rem', bgcolor: col.bg, color: col.color, fontWeight: 600 }}
                />
              </Box>
            )
          })}
        </Box>
      )}
    </Box>
  )
}
