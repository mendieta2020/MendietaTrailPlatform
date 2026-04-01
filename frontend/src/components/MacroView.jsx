/**
 * MacroView — PR-155
 *
 * Coach macro periodization table: one row per athlete showing their
 * training phase for the current and next week, plus Goal A, injury
 * status, and wellness average.
 *
 * Phase suggestions are computed client-side via suggestPhase().
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  CircularProgress,
  Alert,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableContainer,
  Paper,
  Select,
  MenuItem,
  Tooltip,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  FormGroup,
  FormControlLabel,
  Checkbox,
} from '@mui/material';
import { getTrainingWeeks, upsertTrainingWeek, suggestPhase, listTeams, listLibraries, listPlannedWorkouts } from '../api/p1';
import { bulkCreateAssignments } from '../api/assignments';

// ── Phase meta ────────────────────────────────────────────────────────────────

const PHASES = [
  { value: 'carga',    label: 'Carga',    color: '#16a34a' },
  { value: 'descarga', label: 'Descarga', color: '#ca8a04' },
  { value: 'carrera',  label: 'Carrera',  color: '#ea580c' },
  { value: 'descanso', label: 'Descanso', color: '#94a3b8' },
  { value: 'lesion',   label: 'Lesión',   color: '#dc2626' },
];


// ── Wellness circle ───────────────────────────────────────────────────────────

function WellnessCircle({ avg }) {
  if (avg === null || avg === undefined) {
    return (
      <Tooltip title="Sin datos de wellness">
        <Box sx={{
          width: 16, height: 16, borderRadius: '50%',
          bgcolor: '#e2e8f0', display: 'inline-block',
        }} />
      </Tooltip>
    );
  }
  const color = avg >= 3.5 ? '#16a34a' : avg >= 2.5 ? '#ca8a04' : '#dc2626';
  return (
    <Tooltip title={`Wellness promedio: ${avg.toFixed(1)}/5`}>
      <Box sx={{
        width: 16, height: 16, borderRadius: '50%',
        bgcolor: color, display: 'inline-block',
      }} />
    </Tooltip>
  );
}

// ── Monday helpers ────────────────────────────────────────────────────────────

function toMonday(date) {
  const d = new Date(date);
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d;
}

function formatDate(d) {
  return d.toISOString().slice(0, 10);
}

function addWeeks(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n * 7);
  return formatDate(d);
}

// ── Phase selector cell ───────────────────────────────────────────────────────

function PhaseCell({ athleteId, weekStart, currentPhase, suggestion, orgId, onUpdated }) {
  const [saving, setSaving] = useState(false);

  async function handleChange(e) {
    const phase = e.target.value;
    if (!phase) return;
    setSaving(true);
    try {
      await upsertTrainingWeek(orgId, { athlete_id: athleteId, week_start: weekStart, phase });
      onUpdated(athleteId, weekStart, phase);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Select
      size="small"
      value={currentPhase || ''}
      onChange={handleChange}
      displayEmpty
      disabled={saving}
      renderValue={(val) => {
        if (!val) {
          return (
            <Typography variant="caption" sx={{ color: '#94a3b8', fontStyle: 'italic' }}>
              {suggestion ? `Sugerido: ${PHASES.find((p) => p.value === suggestion)?.label}` : 'Sin fase'}
            </Typography>
          );
        }
        const meta = PHASES.find((p) => p.value === val);
        return (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: meta?.color }} />
            <Typography variant="caption" fontWeight={600}>{meta?.label}</Typography>
          </Box>
        );
      }}
      sx={{ minWidth: 130 }}
    >
      <MenuItem value=""><em>— Sin fase —</em></MenuItem>
      {PHASES.map((p) => (
        <MenuItem key={p.value} value={p.value}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: p.color }} />
            {p.label}
          </Box>
        </MenuItem>
      ))}
    </Select>
  );
}

// ── Bulk assign modal ─────────────────────────────────────────────────────────

const DAYS_OF_WEEK = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

function BulkAssignModal({ open, onClose, orgId, weekStart, athletes }) {
  const [libraries, setLibraries] = useState([]);
  const [selectedLib, setSelectedLib] = useState('');
  const [workouts, setWorkouts] = useState([]);
  const [selectedWorkout, setSelectedWorkout] = useState('');
  const [selectedDays, setSelectedDays] = useState([0, 2, 4]); // Mon, Wed, Fri
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!open) return;
    listLibraries(orgId).then((res) => setLibraries(res.data?.results || res.data || []));
  }, [open, orgId]);

  useEffect(() => {
    if (!selectedLib) { setWorkouts([]); return; }
    listPlannedWorkouts(orgId, selectedLib).then((res) => {
      setWorkouts(res.data?.results || res.data || []);
    });
  }, [selectedLib, orgId]);

  function toggleDay(idx) {
    setSelectedDays((prev) =>
      prev.includes(idx) ? prev.filter((d) => d !== idx) : [...prev, idx]
    );
  }

  async function handleAssign() {
    if (!selectedWorkout || selectedDays.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const monday = new Date(weekStart);
      const dates = selectedDays.map((d) => {
        const dt = new Date(monday);
        dt.setDate(dt.getDate() + d);
        return formatDate(dt);
      });
      const athleteIds = athletes.map((a) => a.athlete_id);
      await bulkCreateAssignments(orgId, {
        planned_workout_id: selectedWorkout,
        athlete_ids: athleteIds,
        dates,
      });
      setSuccess(true);
      setTimeout(() => { setSuccess(false); onClose(); }, 1200);
    } catch {
      setError('Error al asignar. Verificá los datos e intentá de nuevo.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        Planificar semana del {weekStart}
      </DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>Entrenamientos asignados.</Alert>}

        <FormControl fullWidth size="small" sx={{ mb: 2, mt: 1 }}>
          <InputLabel>Librería</InputLabel>
          <Select value={selectedLib} label="Librería" onChange={(e) => { setSelectedLib(e.target.value); setSelectedWorkout(''); }}>
            {libraries.map((l) => (
              <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Entrenamiento</InputLabel>
          <Select value={selectedWorkout} label="Entrenamiento" onChange={(e) => setSelectedWorkout(e.target.value)} disabled={!selectedLib}>
            {workouts.map((w) => (
              <MenuItem key={w.id} value={w.id}>{w.title || w.name}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Typography variant="caption" sx={{ color: '#6b7280', mb: 1, display: 'block' }}>
          Días de la semana (respeta días bloqueados de cada atleta):
        </Typography>
        <FormGroup row>
          {DAYS_OF_WEEK.map((day, idx) => (
            <FormControlLabel
              key={idx}
              control={
                <Checkbox
                  size="small"
                  checked={selectedDays.includes(idx)}
                  onChange={() => toggleDay(idx)}
                />
              }
              label={day}
            />
          ))}
        </FormGroup>

        <Typography variant="caption" sx={{ color: '#94a3b8', mt: 1, display: 'block' }}>
          Se asignará a {athletes.length} atleta{athletes.length !== 1 ? 's' : ''}.
          Podés personalizar 1×1 desde la vista Mes.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancelar</Button>
        <Button
          variant="contained"
          onClick={handleAssign}
          disabled={!selectedWorkout || selectedDays.length === 0 || saving}
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
        >
          {saving ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : 'Asignar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main MacroView ────────────────────────────────────────────────────────────

export default function MacroView({ orgId }) {
  const thisMonday = formatDate(toMonday(new Date()));
  const nextMonday = addWeeks(thisMonday, 1);

  const [teamId, setTeamId] = useState('');
  const [teams, setTeams] = useState([]);
  const [rows, setRows] = useState([]);           // current week
  const [rowsNext, setRowsNext] = useState([]);   // next week
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);

  // Load teams
  useEffect(() => {
    if (!orgId) return;
    listTeams(orgId).then((res) => setTeams(res.data?.results || res.data || []));
  }, [orgId]);

  const load = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    setError(null);
    try {
      const [r1, r2] = await Promise.all([
        getTrainingWeeks(orgId, thisMonday, teamId || null),
        getTrainingWeeks(orgId, nextMonday, teamId || null),
      ]);
      setRows(r1.data || []);
      setRowsNext(r2.data || []);
    } catch {
      setError('Error al cargar la vista macro.');
    } finally {
      setLoading(false);
    }
  }, [orgId, thisMonday, nextMonday, teamId]);

  useEffect(() => { load(); }, [load]);

  function handlePhaseUpdated(athleteId, weekStart, phase) {
    const setter = weekStart === thisMonday ? setRows : setRowsNext;
    setter((prev) =>
      prev.map((r) =>
        r.athlete_id === athleteId ? { ...r, phase, training_week_id: r.training_week_id || -1 } : r
      )
    );
  }

  // Map next-week rows by athleteId for quick lookup
  const nextWeekMap = Object.fromEntries((rowsNext || []).map((r) => [r.athlete_id, r]));

  const displayRows = rows;

  return (
    <Box>
      {/* ── Filters ── */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Grupo</InputLabel>
          <Select value={teamId} label="Grupo" onChange={(e) => setTeamId(e.target.value)}>
            <MenuItem value="">Todos los atletas</MenuItem>
            {teams.map((t) => (
              <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Button
          variant="outlined"
          size="small"
          onClick={load}
          disabled={loading}
          sx={{ borderColor: '#F57C00', color: '#F57C00' }}
        >
          Actualizar
        </Button>

        <Box sx={{ flex: 1 }} />

        <Button
          variant="contained"
          size="small"
          onClick={() => setBulkOpen(true)}
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
        >
          Planificar Sem. {thisMonday}
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress sx={{ color: '#F57C00' }} />
        </Box>
      ) : (
        <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#f8fafc' }}>
                <TableCell sx={{ fontWeight: 700 }}>Atleta</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Sem. actual ({thisMonday})</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Sem. siguiente ({nextMonday})</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Carrera A</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Faltan</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Lesión</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Wellness</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {displayRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4, color: '#94a3b8' }}>
                    Sin atletas para mostrar.
                  </TableCell>
                </TableRow>
              )}
              {displayRows.map((row) => {
                const nextRow = nextWeekMap[row.athlete_id] || {};
                const suggestion = suggestPhase(
                  null, // could pass last 3 weeks from a richer API
                  false,
                  row.has_active_injury,
                );
                const nextSuggestion = suggestPhase(null, false, row.has_active_injury);

                return (
                  <TableRow key={row.athlete_id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>
                        {row.athlete_name}
                      </Typography>
                    </TableCell>

                    {/* Current week phase */}
                    <TableCell>
                      <PhaseCell
                        athleteId={row.athlete_id}
                        weekStart={thisMonday}
                        currentPhase={row.phase}
                        suggestion={suggestion}
                        orgId={orgId}
                        onUpdated={handlePhaseUpdated}
                      />
                    </TableCell>

                    {/* Next week phase */}
                    <TableCell>
                      <PhaseCell
                        athleteId={row.athlete_id}
                        weekStart={nextMonday}
                        currentPhase={nextRow.phase}
                        suggestion={nextSuggestion}
                        orgId={orgId}
                        onUpdated={handlePhaseUpdated}
                      />
                    </TableCell>

                    {/* Goal A */}
                    <TableCell>
                      {row.goal_a_title ? (
                        <Tooltip title={row.goal_a_date ? `Fecha: ${row.goal_a_date}` : ''}>
                          <Typography variant="caption" sx={{ maxWidth: 160, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {row.goal_a_title}
                          </Typography>
                        </Tooltip>
                      ) : (
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>—</Typography>
                      )}
                    </TableCell>

                    {/* Days until race */}
                    <TableCell>
                      {row.days_until_race !== null && row.days_until_race !== undefined ? (
                        <Chip
                          label={`${row.days_until_race}d`}
                          size="small"
                          sx={{
                            bgcolor: row.days_until_race <= 7 ? '#fef2f2' : row.days_until_race <= 21 ? '#fff7ed' : '#f0fdf4',
                            color: row.days_until_race <= 7 ? '#dc2626' : row.days_until_race <= 21 ? '#ea580c' : '#16a34a',
                            fontWeight: 600,
                            fontSize: '0.7rem',
                          }}
                        />
                      ) : (
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>—</Typography>
                      )}
                    </TableCell>

                    {/* Active injury */}
                    <TableCell>
                      {row.has_active_injury ? (
                        <Chip label="Activa" size="small" sx={{ bgcolor: '#fef2f2', color: '#dc2626', fontWeight: 600, fontSize: '0.7rem' }} />
                      ) : (
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>—</Typography>
                      )}
                    </TableCell>

                    {/* Wellness */}
                    <TableCell>
                      <WellnessCircle avg={row.wellness_avg} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <BulkAssignModal
        open={bulkOpen}
        onClose={() => setBulkOpen(false)}
        orgId={orgId}
        weekStart={thisMonday}
        athletes={displayRows}
      />
    </Box>
  );
}
