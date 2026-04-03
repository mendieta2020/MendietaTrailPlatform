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
  Divider,
  Snackbar,
} from '@mui/material';
import { getTrainingWeeks, upsertTrainingWeek, suggestPhase, listTeams, listLibraries, listPlannedWorkouts } from '../api/p1';
import { bulkCreateAssignments } from '../api/assignments';
import { autoPeriodizeGroup, getRecentWorkouts } from '../api/periodization';

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
  const dayOfWeek = d.getDay(); // 0=Sun
  d.setDate(d.getDate() - ((dayOfWeek + 6) % 7)); // ISO: Mon=0 offset
  return d;
}

// Local-date formatting — avoids UTC-3 shift from toISOString()
function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function addWeeks(dateStr, n) {
  const d = new Date(dateStr + 'T12:00:00'); // noon prevents DST shifts
  d.setDate(d.getDate() + n * 7);
  return formatDate(d);
}

// ISO week number (UTC-Thursday algorithm)
function isoWeekNumber(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const dow = d.getUTCDay() || 7; // Mon=1…Sun=7
  d.setUTCDate(d.getUTCDate() + 4 - dow); // shift to Thursday
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

const MONTHS_SHORT = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

// "W14 (31 Mar — 6 Abr)"
function formatWeekLabel(weekStart) {
  const d = new Date(weekStart + 'T12:00:00');
  const end = new Date(d);
  end.setDate(end.getDate() + 6);
  const wNum = isoWeekNumber(weekStart);
  return `W${wNum} (${d.getDate()} ${MONTHS_SHORT[d.getMonth()]} — ${end.getDate()} ${MONTHS_SHORT[end.getMonth()]})`;
}

// "W10 (2 Mar)" — short prefix for panel rows
function weekPrefixLabel(weekStart) {
  const d = new Date(weekStart + 'T12:00:00');
  return `W${isoWeekNumber(weekStart)} (${d.getDate()} ${MONTHS_SHORT[d.getMonth()]})`;
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

// ── Cycle patterns ────────────────────────────────────────────────────────────

const CYCLE_OPTIONS = [
  { value: '1:1', label: '1:1 — Principiante (5–15 km)' },
  { value: '2:1', label: '2:1 — Intermedio (21 km)' },
  { value: '3:1', label: '3:1 — Avanzado (42 km+)' },
  { value: '4:1', label: '4:1 — Ultra (80 km+)' },
];

// ── Auto-periodize modal ──────────────────────────────────────────────────────

function AutoPeriodizeModal({ open, onClose, orgId, teams, onSuccess }) {
  const [teamId, setTeamId] = useState('');
  const [defaultCycle, setDefaultCycle] = useState('3:1');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  function handleClose() {
    if (saving) return;
    setResult(null);
    setError(null);
    onClose();
  }

  async function handleSubmit() {
    setSaving(true);
    setError(null);
    try {
      const res = await autoPeriodizeGroup(orgId, {
        team_id: teamId || undefined,
        default_cycle: defaultCycle,
      });
      setResult(res.data);
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al auto-periodizar. Verificá los datos.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Auto-periodizar equipo</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {result ? (
          <Box>
            <Alert severity="success" sx={{ mb: 2 }}>
              <strong>{result.periodized}</strong> atleta{result.periodized !== 1 ? 's' : ''} periodizados.
              {result.skipped_no_goals > 0 && (
                <> <strong>{result.skipped_no_goals}</strong> sin objetivo (saltados).</>
              )}
            </Alert>
            {result.athletes?.map((a) => (
              <Box key={a.athlete_name} sx={{ display: 'flex', justifyContent: 'space-between', py: 0.5 }}>
                <Typography variant="caption">{a.athlete_name}</Typography>
                <Typography variant="caption" sx={{ color: '#6b7280' }}>
                  ciclo {a.cycle} · {a.weeks_created + a.weeks_updated} semanas
                </Typography>
              </Box>
            ))}
          </Box>
        ) : (
          <Box sx={{ pt: 1 }}>
            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Grupo</InputLabel>
              <Select value={teamId} label="Grupo" onChange={(e) => setTeamId(e.target.value)}>
                <MenuItem value="">Todos los atletas</MenuItem>
                {teams.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Ciclo por defecto</InputLabel>
              <Select
                value={defaultCycle}
                label="Ciclo por defecto"
                onChange={(e) => setDefaultCycle(e.target.value)}
              >
                {CYCLE_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Alert severity="info" sx={{ fontSize: '0.75rem' }}>
              El sistema asigna fases automáticamente basándose en los objetivos de carrera
              de cada atleta. El ciclo se ajusta según la distancia del objetivo.
            </Alert>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saving}>
          {result ? 'Cerrar' : 'Cancelar'}
        </Button>
        {!result && (
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={saving}
            sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
          >
            {saving ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : 'Auto-periodizar'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

// ── Recent workouts panel (inside BulkAssignModal) ────────────────────────────

function RecentWorkoutsPanel({ athletes }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!athletes || athletes.length === 0) return;
    // Fetch for the first athlete that has a membership_id; show group-level summary
    const firstWithMembership = athletes.find((a) => a.membership_id);
    if (!firstWithMembership) return;
    let cancelled = false;
    getRecentWorkouts(firstWithMembership.membership_id, 6)
      .then((res) => { if (!cancelled) setData(res.data); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [athletes]);

  if (!data) return null;

  const { weeks, repeated_alerts } = data;

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: '#374151', display: 'block', mb: 1 }}>
        ÚLTIMAS 6 SEMANAS
      </Typography>
      <Box sx={{
        border: '1px solid #e5e7eb', borderRadius: 1, p: 1.5,
        bgcolor: '#f9fafb', fontSize: '0.72rem',
      }}>
        {weeks.filter((w) => w.workouts.length > 0).slice(-6).map((w, i, arr) => (
          <Box key={w.week_start} sx={{
            display: 'flex', gap: 1, py: 0.4,
            borderBottom: i < arr.length - 1 ? '1px solid #f0f0f0' : 'none',
          }}>
            <Typography variant="caption" sx={{ color: '#6b7280', minWidth: 90, flexShrink: 0 }}>
              {weekPrefixLabel(w.week_start)}:
            </Typography>
            <Typography variant="caption" sx={{ color: '#374151' }}>
              {w.workouts.join(', ')}
            </Typography>
          </Box>
        ))}
        {weeks.every((w) => w.workouts.length === 0) && (
          <Typography variant="caption" sx={{ color: '#94a3b8' }}>Sin entrenamientos asignados</Typography>
        )}
      </Box>

      {repeated_alerts.length > 0 && (
        <Alert severity="warning" sx={{ mt: 1, py: 0.5, fontSize: '0.72rem' }}>
          {repeated_alerts.map((a) => (
            <Box key={a.workout}>
              ⚠ <strong>"{a.workout}"</strong> — {a.warning}
            </Box>
          ))}
        </Alert>
      )}

      <Divider sx={{ mt: 1.5, mb: 1 }} />
    </Box>
  );
}

// ── Bulk assign modal ─────────────────────────────────────────────────────────

const DAYS_OF_WEEK = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

function BulkAssignModal({ open, onClose, orgId, weekStart, athletes }) {
  const [libraries, setLibraries] = useState([]);
  const [selectedLib, setSelectedLib] = useState('');
  const [workouts, setWorkouts] = useState([]);
  const [selectedWorkouts, setSelectedWorkouts] = useState([]);
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

  function toggleWorkout(id) {
    setSelectedWorkouts((prev) =>
      prev.includes(id) ? prev.filter((w) => w !== id) : [...prev, id]
    );
  }

  async function handleAssign() {
    if (selectedWorkouts.length === 0 || selectedDays.length === 0) return;
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
      await Promise.all(
        selectedWorkouts.map((wId) =>
          bulkCreateAssignments(orgId, {
            planned_workout_id: wId,
            athlete_ids: athleteIds,
            dates,
          })
        )
      );
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
        Planificar {formatWeekLabel(weekStart)}
      </DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>Entrenamientos asignados.</Alert>}

        {/* PR-157: Recent workouts history */}
        <RecentWorkoutsPanel athletes={athletes} />

        <FormControl fullWidth size="small" sx={{ mb: 2, mt: 1 }}>
          <InputLabel>Librería</InputLabel>
          <Select value={selectedLib} label="Librería" onChange={(e) => { setSelectedLib(e.target.value); setSelectedWorkouts([]); }}>
            {libraries.map((l) => (
              <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Typography variant="caption" sx={{ color: '#6b7280', mb: 1, display: 'block' }}>
          Entrenamientos (seleccioná uno o más):
        </Typography>
        <FormGroup sx={{ mb: 2, pl: 1 }}>
          {workouts.map((w) => (
            <FormControlLabel
              key={w.id}
              control={
                <Checkbox
                  size="small"
                  checked={selectedWorkouts.includes(w.id)}
                  onChange={() => toggleWorkout(w.id)}
                  disabled={!selectedLib}
                />
              }
              label={<Typography variant="caption">{w.title || w.name}</Typography>}
            />
          ))}
          {selectedLib && workouts.length === 0 && (
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>Sin entrenamientos en esta librería.</Typography>
          )}
        </FormGroup>

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
          {selectedWorkouts.length > 0 ? `${selectedWorkouts.length} entrenamiento(s) · ` : ''}
          Se asignará a {athletes.length} atleta{athletes.length !== 1 ? 's' : ''}.
          Podés personalizar 1×1 desde la vista Mes.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancelar</Button>
        <Button
          variant="contained"
          onClick={handleAssign}
          disabled={selectedWorkouts.length === 0 || selectedDays.length === 0 || saving}
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
  const thisMonday = formatDate(toMonday(new Date())); // anchor: today's Monday

  // ── Week window navigation ────────────────────────────────────────────────────
  // windowOffset = weeks to shift the 3-column view from today's Monday
  const [windowOffset, setWindowOffset] = useState(0);
  const week0 = addWeeks(thisMonday, windowOffset);
  const week1 = addWeeks(thisMonday, windowOffset + 1);
  const week2 = addWeeks(thisMonday, windowOffset + 2);

  // "Planificar" button targets next week when today is Wed (getDay≥3) or later
  const planWeek = new Date().getDay() >= 3 ? addWeeks(thisMonday, 1) : thisMonday;

  const [teamId, setTeamId] = useState('');
  const [teams, setTeams] = useState([]);
  const [rows, setRows] = useState([]);           // week0
  const [rowsNext, setRowsNext] = useState([]);   // week1
  const [rowsNext2, setRowsNext2] = useState([]); // week2
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [autoOpen, setAutoOpen] = useState(false);
  // Per-athlete cycle override map: { athleteId: "3:1" }
  const [cycleMap, setCycleMap] = useState({});

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
      const [r1, r2, r3] = await Promise.all([
        getTrainingWeeks(orgId, week0, teamId || null),
        getTrainingWeeks(orgId, week1, teamId || null),
        getTrainingWeeks(orgId, week2, teamId || null),
      ]);
      setRows(r1.data || []);
      setRowsNext(r2.data || []);
      setRowsNext2(r3.data || []);
    } catch {
      setError('Error al cargar la vista macro.');
    } finally {
      setLoading(false);
    }
  }, [orgId, week0, week1, week2, teamId]);

  useEffect(() => { load(); }, [load]);

  // ── Bulk-assign modal target week ─────────────────────────────────────────────
  // null = fall back to planWeek (smart default); set explicitly on header click
  const [bulkWeekStart, setBulkWeekStart] = useState(null);

  function openBulkModal(weekStart) {
    setBulkWeekStart(weekStart);
    setBulkOpen(true);
  }

  function closeBulkModal() {
    setBulkOpen(false);
    setBulkWeekStart(null); // reset so next open via orange button uses planWeek
  }

  function handlePhaseUpdated(athleteId, weekStart, phase) {
    const setter = weekStart === week0 ? setRows
      : weekStart === week1 ? setRowsNext
      : setRowsNext2;
    setter((prev) =>
      prev.map((r) =>
        r.athlete_id === athleteId ? { ...r, phase, training_week_id: r.training_week_id || -1 } : r
      )
    );
  }

  // Map next-week rows by athleteId for quick lookup
  const nextWeekMap = Object.fromEntries((rowsNext || []).map((r) => [r.athlete_id, r]));
  const next2WeekMap = Object.fromEntries((rowsNext2 || []).map((r) => [r.athlete_id, r]));

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

        {/* ── Week window navigation ── */}
        <Button
          size="small"
          variant="outlined"
          onClick={() => setWindowOffset((o) => o - 1)}
          sx={{ minWidth: 32, px: 1, borderColor: '#d1d5db', color: '#6b7280' }}
        >
          ‹
        </Button>
        {windowOffset !== 0 && (
          <Button
            size="small"
            variant="text"
            onClick={() => setWindowOffset(0)}
            sx={{ color: '#6b7280', fontSize: '0.72rem', minWidth: 36 }}
          >
            Hoy
          </Button>
        )}
        <Button
          size="small"
          variant="outlined"
          onClick={() => setWindowOffset((o) => o + 1)}
          sx={{ minWidth: 32, px: 1, borderColor: '#d1d5db', color: '#6b7280' }}
        >
          ›
        </Button>

        {/* PR-157: Auto-periodize group */}
        <Button
          variant="outlined"
          size="small"
          onClick={() => setAutoOpen(true)}
          sx={{ borderColor: '#7c3aed', color: '#7c3aed' }}
        >
          Auto-periodizar
        </Button>

        <Box sx={{ flex: 1 }} />

        {/* Defaults to next week when today is Wed or later — or click any column header */}
        <Button
          variant="contained"
          size="small"
          onClick={() => openBulkModal(planWeek)}
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' } }}
        >
          Planificar {formatWeekLabel(planWeek)}
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
                {[week0, week1, week2].map((w) => (
                  <TableCell key={w} sx={{ fontWeight: 700, p: 0 }}>
                    <Tooltip title={`Planificar ${formatWeekLabel(w)}`} placement="top">
                      <Box
                        onClick={() => openBulkModal(w)}
                        sx={{
                          cursor: 'pointer',
                          px: 2, py: 1,
                          '&:hover': { color: '#F57C00', textDecoration: 'underline' },
                        }}
                      >
                        {formatWeekLabel(w)}
                      </Box>
                    </Tooltip>
                  </TableCell>
                ))}
                <TableCell sx={{ fontWeight: 700 }}>Próximo Objetivo</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Faltan</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Lesión</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Wellness</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Ciclo</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {displayRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ py: 4, color: '#94a3b8' }}>
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
                const next2Row = next2WeekMap[row.athlete_id] || {};

                return (
                  <TableRow key={row.athlete_id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>
                        {row.athlete_name}
                      </Typography>
                    </TableCell>

                    {/* Week 0 phase */}
                    <TableCell>
                      <PhaseCell
                        athleteId={row.athlete_id}
                        weekStart={week0}
                        currentPhase={row.phase}
                        suggestion={suggestion}
                        orgId={orgId}
                        onUpdated={handlePhaseUpdated}
                      />
                    </TableCell>

                    {/* Week 1 phase */}
                    <TableCell>
                      <PhaseCell
                        athleteId={row.athlete_id}
                        weekStart={week1}
                        currentPhase={nextRow.phase}
                        suggestion={nextSuggestion}
                        orgId={orgId}
                        onUpdated={handlePhaseUpdated}
                      />
                    </TableCell>

                    {/* Week 2 phase */}
                    <TableCell>
                      <PhaseCell
                        athleteId={row.athlete_id}
                        weekStart={week2}
                        currentPhase={next2Row.phase}
                        suggestion={nextSuggestion}
                        orgId={orgId}
                        onUpdated={handlePhaseUpdated}
                      />
                    </TableCell>

                    {/* Next goal (nearest date, any priority) */}
                    <TableCell>
                      {row.goal_a_title ? (
                        <Tooltip
                          title={
                            (row.all_goals_brief || []).length > 1
                              ? (row.all_goals_brief || []).map((g) => `${g.title} (${g.priority})${g.days != null ? ` — ${g.days}d` : ''}`).join(' · ')
                              : (row.goal_a_date ? `Fecha: ${row.goal_a_date}` : '')
                          }
                        >
                          <Box>
                            <Typography variant="caption" sx={{ maxWidth: 160, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>
                              {row.goal_a_title}{row.goal_a_priority ? ` (${row.goal_a_priority})` : ''}
                            </Typography>
                            {(row.goal_a_distance_km || row.goal_a_elevation_m) && (
                              <Typography variant="caption" sx={{ color: '#6b7280', display: 'block', fontSize: '0.65rem' }}>
                                {row.goal_a_distance_km ? `${row.goal_a_distance_km}K` : ''}
                                {row.goal_a_distance_km && row.goal_a_elevation_m ? ' · ' : ''}
                                {row.goal_a_elevation_m ? `D+ ${row.goal_a_elevation_m.toLocaleString()}m` : ''}
                              </Typography>
                            )}
                          </Box>
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

                    {/* PR-157: Cycle per athlete — stored locally, applied via Auto-periodizar */}
                    <TableCell>
                      <Tooltip
                        title={`Ciclo preferido — aplicá con Auto-periodizar${row.goal_a_distance_km ? `. Sugerido: ${suggestPhase(null, false, row.has_active_injury) || '3:1'} (distancia ${row.goal_a_distance_km}K)` : ''}`}
                        placement="top"
                      >
                        <Select
                          size="small"
                          value={cycleMap[row.athlete_id] || '3:1'}
                          onChange={(e) =>
                            setCycleMap((prev) => ({ ...prev, [row.athlete_id]: e.target.value }))
                          }
                          sx={{ minWidth: 80, fontSize: '0.75rem' }}
                        >
                          {['1:1', '2:1', '3:1', '4:1'].map((v) => (
                            <MenuItem key={v} value={v} sx={{ fontSize: '0.75rem' }}>{v}</MenuItem>
                          ))}
                        </Select>
                      </Tooltip>
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
        onClose={closeBulkModal}
        orgId={orgId}
        weekStart={bulkWeekStart ?? planWeek}
        athletes={displayRows}
      />

      {/* PR-157: Auto-periodize group modal */}
      <AutoPeriodizeModal
        open={autoOpen}
        onClose={() => setAutoOpen(false)}
        orgId={orgId}
        teams={teams}
        onSuccess={load}
      />
    </Box>
  );
}
