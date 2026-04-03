/**
 * AthleteGoalsTab — PR-160
 * Coach sees athlete race goals with edit + delete per card.
 */
import React, { useState, useEffect } from 'react'
import {
  Box, Typography, CircularProgress, Alert, Chip,
  TextField, Button, MenuItem,
} from '@mui/material'
import { getCoachAthleteGoals } from '../api/pmc'
import { updateGoal, deleteGoal } from '../api/athlete'
import { useOrg } from '../context/OrgContext'

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

const PRIORITY_OPTIONS = ['A', 'B', 'C']
const STATUS_OPTIONS = [
  { value: 'active', label: 'Activo' },
  { value: 'planned', label: 'Planificado' },
  { value: 'completed', label: 'Completado' },
  { value: 'paused', label: 'Pausado' },
  { value: 'cancelled', label: 'Cancelado' },
]

export default function AthleteGoalsTab({ membershipId }) {
  const { activeOrg } = useOrg()
  const orgId = activeOrg?.org_id ?? null

  const [goals, setGoals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Edit state: goalId → draft object
  const [editingId, setEditingId] = useState(null)
  const [editDraft, setEditDraft] = useState({})
  const [savingId, setSavingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  useEffect(() => {
    if (!membershipId) return
    getCoachAthleteGoals(membershipId)
      .then(res => { setGoals(res.data.results ?? []); setLoading(false) })
      .catch(() => { setError('No se pudieron cargar los objetivos.'); setLoading(false) })
  }, [membershipId])

  const startEdit = (goal) => {
    setEditingId(goal.id)
    setEditDraft({
      title: goal.title ?? '',
      target_date: goal.target_date ?? '',
      priority: goal.priority ?? 'C',
      status: goal.status ?? 'planned',
      target_distance_km: goal.target_distance_km ?? '',
      target_elevation_gain_m: goal.target_elevation_gain_m ?? '',
    })
  }

  const cancelEdit = () => { setEditingId(null); setEditDraft({}) }

  const saveEdit = async (goalId) => {
    if (!orgId) return
    setSavingId(goalId)
    try {
      const payload = {
        title: editDraft.title,
        target_date: editDraft.target_date || null,
        priority: editDraft.priority,
        status: editDraft.status,
        target_distance_km: editDraft.target_distance_km !== '' ? Number(editDraft.target_distance_km) : null,
        target_elevation_gain_m: editDraft.target_elevation_gain_m !== '' ? Number(editDraft.target_elevation_gain_m) : null,
      }
      const res = await updateGoal(orgId, goalId, payload)
      setGoals(prev => prev.map(g => g.id === goalId ? { ...g, ...res.data } : g))
      setEditingId(null)
      setEditDraft({})
    } catch {
      setError('Error al guardar. Intentá de nuevo.')
    } finally {
      setSavingId(null)
    }
  }

  const handleDelete = async (goalId) => {
    if (!orgId) return
    setDeletingId(goalId)
    try {
      await deleteGoal(orgId, goalId)
      setGoals(prev => prev.filter(g => g.id !== goalId))
    } catch {
      setError('Error al eliminar el objetivo.')
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) return <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

      {goals.length === 0 && (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: '#94a3b8' }}>Sin objetivos registrados</Typography>
        </Box>
      )}

      {goals.map(goal => {
        const prio = PRIORITY_COLORS[goal.priority] ?? PRIORITY_COLORS.C
        const stat = STATUS_COLORS[goal.status] ?? STATUS_COLORS.planned
        const isUpcoming = goal.days_remaining !== null && goal.days_remaining >= 0
        const isUrgent = goal.days_remaining !== null && goal.days_remaining <= 7 && isUpcoming
        const isEditing = editingId === goal.id

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
            {isEditing ? (
              /* ── Edit form ── */
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                <TextField
                  label="Nombre"
                  size="small"
                  fullWidth
                  value={editDraft.title}
                  onChange={e => setEditDraft(d => ({ ...d, title: e.target.value }))}
                  sx={{ '& .MuiOutlinedInput-root': { '&.Mui-focused fieldset': { borderColor: '#F57C00' } } }}
                />
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    label="Fecha objetivo"
                    type="date"
                    size="small"
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    value={editDraft.target_date}
                    onChange={e => setEditDraft(d => ({ ...d, target_date: e.target.value }))}
                  />
                  <TextField
                    select
                    label="Prioridad"
                    size="small"
                    sx={{ minWidth: 100 }}
                    value={editDraft.priority}
                    onChange={e => setEditDraft(d => ({ ...d, priority: e.target.value }))}
                  >
                    {PRIORITY_OPTIONS.map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                  </TextField>
                  <TextField
                    select
                    label="Estado"
                    size="small"
                    sx={{ minWidth: 130 }}
                    value={editDraft.status}
                    onChange={e => setEditDraft(d => ({ ...d, status: e.target.value }))}
                  >
                    {STATUS_OPTIONS.map(s => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
                  </TextField>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    label="Distancia (km)"
                    type="number"
                    size="small"
                    fullWidth
                    value={editDraft.target_distance_km}
                    onChange={e => setEditDraft(d => ({ ...d, target_distance_km: e.target.value }))}
                  />
                  <TextField
                    label="Desnivel + (m)"
                    type="number"
                    size="small"
                    fullWidth
                    value={editDraft.target_elevation_gain_m}
                    onChange={e => setEditDraft(d => ({ ...d, target_elevation_gain_m: e.target.value }))}
                  />
                </Box>
                <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                  <Button size="small" onClick={cancelEdit} sx={{ color: '#64748b', fontSize: '0.75rem' }}>
                    Cancelar
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => saveEdit(goal.id)}
                    disabled={savingId === goal.id || !editDraft.title}
                    sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' }, fontSize: '0.75rem' }}
                  >
                    {savingId === goal.id ? <CircularProgress size={12} sx={{ color: '#fff' }} /> : 'Guardar'}
                  </Button>
                </Box>
              </Box>
            ) : (
              /* ── View mode ── */
              <>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 1 }}>
                  <Box sx={{ flex: 1 }}>
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

                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
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
                    {/* Edit + Delete buttons */}
                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                      <Button
                        size="small"
                        onClick={() => startEdit(goal)}
                        sx={{ minWidth: 0, px: 0.75, color: '#64748b', fontSize: '0.7rem' }}
                        title="Editar"
                      >
                        ✏️
                      </Button>
                      <Button
                        size="small"
                        onClick={() => handleDelete(goal.id)}
                        disabled={deletingId === goal.id}
                        sx={{ minWidth: 0, px: 0.75, color: '#ef4444', fontSize: '0.7rem' }}
                        title="Eliminar"
                      >
                        {deletingId === goal.id ? <CircularProgress size={10} sx={{ color: '#ef4444' }} /> : '🗑️'}
                      </Button>
                    </Box>
                  </Box>
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
              </>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
