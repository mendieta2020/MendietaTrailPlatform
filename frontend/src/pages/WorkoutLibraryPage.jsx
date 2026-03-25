import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Paper, Typography, Button, IconButton, Chip, CircularProgress, Alert, Divider, Collapse,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  List, ListItem, ListItemText, ListItemSecondaryAction, ListItemButton,
  Tooltip, Snackbar, Skeleton, Select, MenuItem as MuiMenuItem, FormControl,
  Menu,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  ContentCopy as DuplicateIcon,
  MoreVert as MoreVertIcon,
  FolderOpen as FolderOpenIcon,
  FitnessCenter as FitnessCenterIcon,
  LibraryBooks as LibraryBooksIcon,
  Search as SearchIcon,
  ViewList as ViewListIcon,
  GridView as GridViewIcon,
  CalendarMonth as CalendarIcon,
} from '@mui/icons-material';
import { FolderOpen, Dumbbell } from 'lucide-react';
import Layout from '../components/Layout';
import WorkoutBuilder from '../components/WorkoutBuilder';
import { useOrg } from '../context/OrgContext';
import {
  listLibraries, createLibrary, deleteLibrary,
  listPlannedWorkouts, getPlannedWorkout, createPlannedWorkout,
  createWorkoutBlock, createWorkoutInterval, deletePlannedWorkout,
} from '../api/p1';

const DIFFICULTY_CONFIG = {
  EASY:      { label: 'Fácil',       color: '#22c55e' },
  MODERATE:  { label: 'Moderado',    color: '#f59e0b' },
  HARD:      { label: 'Difícil',     color: '#ef4444' },
  VERY_HARD: { label: 'Muy Difícil', color: '#7c3aed' },
};

const SPORT_CONFIG = {
  TRAIL:    { emoji: '🏔', bg: '#dcfce7', label: 'Trail' },
  RUN:      { emoji: '🏃', bg: '#dbeafe', label: 'Running' },
  BIKE:     { emoji: '🚴', bg: '#ede9fe', label: 'Ciclismo' },
  WALK:     { emoji: '🚶', bg: '#fef9c3', label: 'Caminata' },
  STRENGTH: { emoji: '💪', bg: '#fef3c7', label: 'Fuerza' },
  OTHER:    { emoji: '⚡', bg: '#f1f5f9', label: 'Otro' },
};

const ZONE_COLORS = { Z1: '#3b82f6', Z2: '#22c55e', Z3: '#f59e0b', Z4: '#f97316', Z5: '#ef4444' };
const ZONE_KEYS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5'];

// Compute real zone distribution from nested blocks/intervals returned by API
function computeZoneDist(workout) {
  const secs = { Z1: 0, Z2: 0, Z3: 0, Z4: 0, Z5: 0 };
  let total = 0;
  for (const block of workout.blocks ?? []) {
    const reps = block.block_type === 'REPEAT'
      ? Math.max(1, block.intervals?.[0]?.repetitions ?? 1)
      : 1;
    for (const iv of block.intervals ?? []) {
      const dur = Number(iv.duration_seconds ?? 0);
      const zone = (iv.target_label ?? '').toUpperCase();
      if (ZONE_KEYS.includes(zone)) secs[zone] += dur * reps;
      total += dur * reps;
    }
  }
  if (total === 0) return null;
  return ZONE_KEYS.map((z) => ({ z, pct: secs[z] / total })).filter((x) => x.pct > 0.01);
}

function ZonePreviewBar({ workout }) {
  const dist = computeZoneDist(workout);
  if (!dist) {
    // No zone data — show neutral bar
    return (
      <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', width: 100 }}>
        <div style={{ flex: 1, background: '#e2e8f0', borderRadius: 2 }} />
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', width: 100, gap: 1 }}>
      {dist.map(({ z, pct }) => (
        <div key={z} title={`${z}: ${Math.round(pct * 100)}%`}
          style={{ flex: pct, background: ZONE_COLORS[z], borderRadius: 2 }} />
      ))}
    </div>
  );
}

function SportIconBadge({ sportType }) {
  const cfg = SPORT_CONFIG[sportType] ?? SPORT_CONFIG.OTHER;
  return (
    <div style={{
      width: 36, height: 36, borderRadius: 8, background: cfg.bg,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 18, flexShrink: 0,
    }}>
      {cfg.emoji}
    </div>
  );
}

function DifficultyChip({ value }) {
  const cfg = DIFFICULTY_CONFIG[value] ?? { label: value, color: '#94a3b8' };
  return (
    <Chip
      label={cfg.label}
      size="small"
      sx={{ bgcolor: `${cfg.color}20`, color: cfg.color, fontWeight: 600, fontSize: '0.7rem', border: `1px solid ${cfg.color}40` }}
    />
  );
}

function fmtDuration(minutes) {
  if (!minutes) return null;
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const SPORT_FILTER_OPTS = [
  { value: 'ALL', label: 'Todos' },
  { value: 'TRAIL', label: '🏔 Trail' },
  { value: 'RUN', label: '🏃 Run' },
  { value: 'BIKE', label: '🚴 Bici' },
  { value: 'STRENGTH', label: '💪 Fuerza' },
];

export default function WorkoutLibraryPage() {
  const { activeOrg, orgLoading } = useOrg();
  const orgId = activeOrg?.org_id;

  // ── Libraries state ─────────────────────────────────────────────────────────
  const [libraries, setLibraries] = useState([]);
  const [libLoading, setLibLoading] = useState(false);
  const [libError, setLibError] = useState('');

  // ── New library dialog ──────────────────────────────────────────────────────
  const [newLibOpen, setNewLibOpen] = useState(false);
  const [newLibName, setNewLibName] = useState('');
  const [newLibDesc, setNewLibDesc] = useState('');
  const [newLibSaving, setNewLibSaving] = useState(false);
  const [newLibError, setNewLibError] = useState('');

  // ── Selected library / workouts ─────────────────────────────────────────────
  const [selectedLibId, setSelectedLibId] = useState(null);
  const [workouts, setWorkouts] = useState([]);
  const [workoutsLoading, setWorkoutsLoading] = useState(false);

  // ── Workout builder ─────────────────────────────────────────────────────────
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editWorkout, setEditWorkout] = useState(null);   // full workout for edit mode


  // ── Search / filter / sort ───────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [sportFilter, setSportFilter] = useState('ALL');
  const [difficultyFilter, setDifficultyFilter] = useState('ALL');
  const [sortBy, setSortBy] = useState('recent');

  // ── Snackbar ────────────────────────────────────────────────────────────────
  const [snackbar, setSnackbar] = useState({ open: false, msg: '', severity: 'success' });
  const toast = (msg, severity = 'success') => setSnackbar({ open: true, msg, severity });

  // ── Data fetching ───────────────────────────────────────────────────────────

  const fetchLibraries = useCallback(async () => {
    if (!orgId) return;
    setLibLoading(true);
    setLibError('');
    try {
      const res = await listLibraries(orgId);
      setLibraries(res.data?.results ?? res.data ?? []);
    } catch {
      setLibError('No se pudieron cargar las librerías.');
    } finally {
      setLibLoading(false);
    }
  }, [orgId]);

  const fetchWorkouts = useCallback(async (libId) => {
    if (!orgId || !libId) return;
    setWorkoutsLoading(true);
    try {
      const res = await listPlannedWorkouts(orgId, libId);
      setWorkouts(res.data?.results ?? res.data ?? []);
    } catch {
      toast('No se pudieron cargar los entrenamientos.', 'error');
    } finally {
      setWorkoutsLoading(false);
    }
  }, [orgId]);

  useEffect(() => { fetchLibraries(); }, [fetchLibraries]);

  useEffect(() => {
    if (selectedLibId) fetchWorkouts(selectedLibId);
    else setWorkouts([]);
  }, [selectedLibId, fetchWorkouts]);

  // ── Library CRUD ────────────────────────────────────────────────────────────

  const handleCreateLibrary = async () => {
    if (!newLibName.trim()) { setNewLibError('El nombre es obligatorio.'); return; }
    setNewLibSaving(true);
    setNewLibError('');
    try {
      await createLibrary(orgId, { name: newLibName.trim(), description: newLibDesc.trim() });
      setNewLibOpen(false);
      setNewLibName('');
      setNewLibDesc('');
      await fetchLibraries();
      toast('Librería creada correctamente.');
    } catch (err) {
      setNewLibError(err?.response?.data?.name?.[0] ?? 'Error al crear la librería.');
    } finally {
      setNewLibSaving(false);
    }
  };

  const handleDeleteLibrary = async (libId) => {
    if (!window.confirm('¿Eliminar esta librería y todos sus entrenamientos?')) return;
    try {
      await deleteLibrary(orgId, libId);
      if (selectedLibId === libId) setSelectedLibId(null);
      await fetchLibraries();
      toast('Librería eliminada.');
    } catch {
      toast('Error al eliminar la librería.', 'error');
    }
  };

  // ── Workout CRUD ────────────────────────────────────────────────────────────

  const handleDeleteWorkout = async (workoutId) => {
    if (!window.confirm('¿Eliminar este entrenamiento?')) return;
    try {
      await deletePlannedWorkout(orgId, selectedLibId, workoutId);
      setWorkouts((prev) => prev.filter((w) => w.id !== workoutId));
      toast('Entrenamiento eliminado.');
    } catch {
      toast('Error al eliminar el entrenamiento.', 'error');
    }
  };

  const handleWorkoutSaved = (workout) => {
    setWorkouts((prev) => [workout, ...prev]);
    toast('Entrenamiento creado correctamente.');
  };

  const handleWorkoutUpdated = (workout) => {
    setWorkouts((prev) => prev.map((w) => (w.id === workout.id ? workout : w)));
    toast('Entrenamiento actualizado.');
  };

  const handleEditWorkout = async (workoutId) => {
    try {
      const res = await getPlannedWorkout(orgId, selectedLibId, workoutId);
      setEditWorkout(res.data);
      setBuilderOpen(true);
    } catch {
      toast('No se pudo cargar el entrenamiento para editar.', 'error');
    }
  };

  const handleDuplicateWorkout = async (workoutId) => {
    try {
      const res = await getPlannedWorkout(orgId, selectedLibId, workoutId);
      const src = res.data;

      // Create duplicate workout with "(Copia)" suffix
      const newWorkoutPayload = {
        name: `${src.name} (Copia)`,
        description: src.description ?? '',
        discipline: src.discipline,
        session_type: src.session_type,
        ...(src.estimated_duration_seconds && { estimated_duration_seconds: src.estimated_duration_seconds }),
        ...(src.estimated_distance_meters && { estimated_distance_meters: src.estimated_distance_meters }),
      };
      const newWorkoutRes = await createPlannedWorkout(orgId, selectedLibId, newWorkoutPayload);
      const newWorkoutId = newWorkoutRes.data.id;

      // Recreate blocks + intervals from source
      for (const block of src.blocks ?? []) {
        const blockRes = await createWorkoutBlock(orgId, selectedLibId, newWorkoutId, {
          name: block.name,
          block_type: block.block_type,
          order_index: block.order_index,
        });
        const newBlockId = blockRes.data.id;
        for (const iv of block.intervals ?? []) {
          await createWorkoutInterval(orgId, selectedLibId, newWorkoutId, newBlockId, {
            order_index: iv.order_index,
            repetitions: iv.repetitions ?? 1,
            metric_type: iv.metric_type,
            description: iv.description ?? '',
            ...(iv.duration_seconds != null && { duration_seconds: iv.duration_seconds }),
            ...(iv.distance_meters != null && { distance_meters: iv.distance_meters }),
            ...(iv.target_label && { target_label: iv.target_label }),
            ...(iv.recovery_seconds != null && { recovery_seconds: iv.recovery_seconds }),
          });
        }
      }

      setWorkouts((prev) => [newWorkoutRes.data, ...prev]);
      toast('Entrenamiento duplicado correctamente.');
    } catch {
      toast('Error al duplicar el entrenamiento.', 'error');
    }
  };

  // ── Toggle library selection ────────────────────────────────────────────────
  const handleToggleLibrary = (libId) => {
    setSelectedLibId((prev) => (prev === libId ? null : libId));
    setSearchQuery('');
    setSportFilter('ALL');
    setDifficultyFilter('ALL');
  };

  // ── Selected library object ─────────────────────────────────────────────────
  const selectedLib = libraries.find((l) => l.id === selectedLibId);

  // ── Filtered + sorted workouts ───────────────────────────────────────────────
  const filteredWorkouts = useMemo(() => {
    let list = [...workouts];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((w) => w.name?.toLowerCase().includes(q) || w.description?.toLowerCase().includes(q));
    }
    if (sportFilter !== 'ALL') {
      list = list.filter((w) => (w.discipline ?? w.sport_type ?? '').toUpperCase() === sportFilter);
    }
    if (difficultyFilter !== 'ALL') {
      list = list.filter((w) => (w.difficulty ?? '') === difficultyFilter);
    }
    if (sortBy === 'az') list.sort((a, b) => a.name.localeCompare(b.name));
    else if (sortBy === 'duration') list.sort((a, b) => (b.estimated_duration_minutes ?? 0) - (a.estimated_duration_minutes ?? 0));
    else if (sortBy === 'distance') list.sort((a, b) => (b.estimated_distance_km ?? 0) - (a.estimated_distance_km ?? 0));
    // default 'recent' = API order (already newest first)
    return list;
  }, [workouts, searchQuery, sportFilter, difficultyFilter, sortBy]);

  // ── Loading guard ────────────────────────────────────────────────────────────
  if (orgLoading) {
    return (
      <Layout>
        <div className="flex justify-center mt-10">
          <CircularProgress />
        </div>
      </Layout>
    );
  }

  if (!activeOrg) {
    return (
      <Layout>
        <Alert severity="warning" sx={{ mt: 4 }}>
          Selecciona una organización para ver la librería de entrenamientos.
        </Alert>
      </Layout>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <Layout>
      {/* ── Page Header ── */}
      <div className="flex items-start gap-2 mb-4">
        <LibraryBooksIcon sx={{ color: '#f59e0b', mt: 0.5 }} />
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Librería de Entrenamientos</h1>
          <p className="text-sm text-slate-500">
            {activeOrg.org_name} · Diseña y organiza tus rutinas estructuradas
          </p>
        </div>
      </div>

      {libError && <Alert severity="error" sx={{ mb: 2 }}>{libError}</Alert>}

      {/* ── 2-Column Layout ── */}
      <Box sx={{ display: 'flex', gap: 3, alignItems: 'flex-start', minHeight: '70vh' }}>

        {/* ── LEFT COLUMN: Folders ── */}
        <Paper elevation={2} sx={{ width: 280, flexShrink: 0, borderRadius: 2, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {/* Header */}
          <Box sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'grey.200' }}>
            <Typography variant="caption" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, color: 'text.secondary' }}>
              Carpetas
            </Typography>
          </Box>

          {/* Library list */}
          <Box sx={{ flex: 1, overflowY: 'auto', py: 0.5 }}>
            {libLoading ? (
              <Box sx={{ px: 2, py: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} variant="rounded" height={40} />
                ))}
              </Box>
            ) : libraries.length === 0 ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', py: 5, px: 2, textAlign: 'center' }}>
                <FolderOpenIcon sx={{ color: 'grey.300', fontSize: 36, mb: 1 }} />
                <Typography variant="caption" color="text.disabled">Sin carpetas aún</Typography>
              </Box>
            ) : (
              <List disablePadding dense>
                {libraries.map((lib) => {
                  const isSelected = selectedLibId === lib.id;
                  return (
                    <ListItemButton
                      key={lib.id}
                      selected={isSelected}
                      onClick={() => handleToggleLibrary(lib.id)}
                      sx={{
                        px: 2,
                        py: 1,
                        borderLeft: isSelected ? '3px solid #f59e0b' : '3px solid transparent',
                        bgcolor: isSelected ? 'grey.100' : 'transparent',
                        '&:hover': { bgcolor: 'grey.50' },
                        '&.Mui-selected': { bgcolor: 'grey.100' },
                        '&.Mui-selected:hover': { bgcolor: 'grey.200' },
                      }}
                    >
                      <FolderOpenIcon
                        sx={{ fontSize: 16, mr: 1.5, flexShrink: 0, color: isSelected ? '#f59e0b' : 'text.disabled' }}
                      />
                      <ListItemText
                        primary={lib.name}
                        secondary={`${lib.workout_count ?? 0} entrenos`}
                        primaryTypographyProps={{
                          fontSize: '0.8125rem',
                          fontWeight: isSelected ? 700 : 400,
                          noWrap: true,
                          color: isSelected ? 'text.primary' : 'text.secondary',
                        }}
                        secondaryTypographyProps={{ fontSize: '0.6875rem' }}
                      />
                      <Tooltip title="Eliminar carpeta" placement="right">
                        <IconButton
                          size="small"
                          onClick={(e) => { e.stopPropagation(); handleDeleteLibrary(lib.id); }}
                          sx={{
                            p: 0.5,
                            ml: 0.5,
                            opacity: 0,
                            '.MuiListItemButton-root:hover &': { opacity: 1 },
                            '&:hover': { color: 'error.main' },
                          }}
                        >
                          <DeleteIcon sx={{ fontSize: 14 }} />
                        </IconButton>
                      </Tooltip>
                    </ListItemButton>
                  );
                })}
              </List>
            )}
          </Box>

          {/* Add library CTA */}
          <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'grey.200' }}>
            <Button
              fullWidth
              variant="contained"
              size="small"
              startIcon={<AddIcon sx={{ fontSize: 15 }} />}
              onClick={() => setNewLibOpen(true)}
              sx={{
                bgcolor: '#f59e0b',
                '&:hover': { bgcolor: '#d97706' },
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.8rem',
                borderRadius: 1.5,
                boxShadow: 'none',
              }}
            >
              Nueva carpeta
            </Button>
          </Box>
        </Paper>

        {/* ── RIGHT COLUMN: Content ── */}
        <Paper elevation={2} sx={{ flexGrow: 1, borderRadius: 2, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: '70vh' }}>
          {!selectedLibId ? (
            /* No library selected — instructional empty state */
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, py: 12, textAlign: 'center', px: 4 }}>
              <FolderOpen className="w-12 h-12 mb-4" style={{ color: '#cbd5e1' }} />
              <Typography variant="h6" fontWeight={600} color="text.secondary" gutterBottom>
                Selecciona una carpeta
              </Typography>
              <Typography variant="body2" color="text.disabled">
                Elige una librería del panel izquierdo para ver y gestionar sus entrenamientos.
              </Typography>
            </Box>
          ) : (
            <>
              {/* ── Toolbar: breadcrumb + search + filters + sort + CTA ── */}
              <Box sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'grey.100', display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
                {/* Breadcrumb */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mr: 0.5, flexShrink: 0 }}>
                  <FolderOpenIcon sx={{ color: '#f59e0b', fontSize: 16 }} />
                  <Typography variant="body2" fontWeight={700} color="text.primary" noWrap sx={{ maxWidth: 120 }}>
                    {selectedLib?.name}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    · {workouts.length}
                  </Typography>
                </Box>

                {/* Search */}
                <Box sx={{
                  display: 'flex', alignItems: 'center', gap: 0.75,
                  background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 2,
                  px: 1.25, py: 0.5, flex: 1, minWidth: 140, maxWidth: 240,
                }}>
                  <SearchIcon sx={{ fontSize: 14, color: '#94a3b8', flexShrink: 0 }} />
                  <input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Buscar…"
                    style={{ border: 'none', background: 'transparent', outline: 'none', fontSize: 12, color: '#1e293b', width: '100%' }}
                  />
                </Box>

                {/* Sport filter pills */}
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'nowrap', overflow: 'auto' }}>
                  {SPORT_FILTER_OPTS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setSportFilter(opt.value)}
                      style={{
                        padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                        cursor: 'pointer', border: '1px solid',
                        whiteSpace: 'nowrap',
                        background: sportFilter === opt.value ? '#fff7ed' : 'white',
                        borderColor: sportFilter === opt.value ? '#f59e0b' : '#e2e8f0',
                        color: sportFilter === opt.value ? '#f59e0b' : '#64748b',
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </Box>

                {/* Difficulty filter pills */}
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'nowrap', overflow: 'auto' }}>
                  {[
                    { value: 'ALL', label: 'Todas' },
                    { value: 'easy', label: '🟢 Fácil' },
                    { value: 'moderate', label: '🟡 Moderado' },
                    { value: 'hard', label: '🟠 Difícil' },
                    { value: 'very_hard', label: '🔴 Muy difícil' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setDifficultyFilter(opt.value)}
                      style={{
                        padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                        cursor: 'pointer', border: '1px solid',
                        whiteSpace: 'nowrap',
                        background: difficultyFilter === opt.value ? '#f0fdf4' : 'white',
                        borderColor: difficultyFilter === opt.value ? '#22c55e' : '#e2e8f0',
                        color: difficultyFilter === opt.value ? '#16a34a' : '#64748b',
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </Box>

                {/* Sort */}
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  style={{
                    background: 'white', border: '1px solid #e2e8f0', borderRadius: 8,
                    padding: '4px 8px', fontSize: 11, color: '#64748b', cursor: 'pointer',
                    outline: 'none', flexShrink: 0,
                  }}
                >
                  <option value="recent">Recientes</option>
                  <option value="az">A–Z</option>
                  <option value="duration">Duración</option>
                  <option value="distance">Distancia</option>
                </select>

                {/* New workout CTA */}
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<AddIcon sx={{ fontSize: 14 }} />}
                  onClick={() => { setEditWorkout(null); setBuilderOpen(true); }}
                  sx={{
                    ml: 'auto', flexShrink: 0, borderRadius: 1.5,
                    bgcolor: '#f59e0b', '&:hover': { bgcolor: '#d97706' },
                    textTransform: 'none', fontWeight: 600, fontSize: '0.75rem',
                    boxShadow: 'none', whiteSpace: 'nowrap',
                  }}
                >
                  Nuevo entrenamiento
                </Button>
              </Box>

              {/* ── Column headers ── */}
              {!workoutsLoading && filteredWorkouts.length > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 0.75, borderBottom: '1px solid', borderColor: 'grey.100', bgcolor: '#f8fafc' }}>
                  <Typography variant="caption" sx={{ flex: 1, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, color: 'text.disabled' }}>
                    Entrenamiento
                  </Typography>
                  <Typography variant="caption" sx={{ width: 108, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, color: 'text.disabled' }}>
                    Zonas
                  </Typography>
                  <Typography variant="caption" sx={{ width: 80, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, color: 'text.disabled', textAlign: 'right' }}>
                    Duración
                  </Typography>
                  <Typography variant="caption" sx={{ width: 72, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, color: 'text.disabled', textAlign: 'right' }}>
                    Dist.
                  </Typography>
                  <Box sx={{ width: 100 }} />
                </Box>
              )}

              {/* ── Workout rows ── */}
              {workoutsLoading ? (
                <Box sx={{ px: 2, py: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {[1, 2, 3, 4].map((i) => <Skeleton key={i} variant="rounded" height={56} />)}
                </Box>
              ) : workouts.length === 0 ? (
                /* Empty state — no workouts in folder */
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, py: 10, textAlign: 'center', px: 4 }}>
                  <Dumbbell className="w-12 h-12 mb-4" style={{ color: '#cbd5e1' }} />
                  <Typography variant="h6" fontWeight={600} color="text.secondary" gutterBottom>
                    Carpeta vacía
                  </Typography>
                  <Typography variant="body2" color="text.disabled" sx={{ mb: 3 }}>
                    Agrega el primer entrenamiento a esta librería.
                  </Typography>
                  <button
                    onClick={() => { setEditWorkout(null); setBuilderOpen(true); }}
                    className="px-4 py-2 text-white text-sm font-medium rounded-lg transition-colors"
                    style={{ background: '#f59e0b' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#d97706')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '#f59e0b')}
                  >
                    Crear primer entrenamiento
                  </button>
                </Box>
              ) : filteredWorkouts.length === 0 ? (
                /* Empty state — search/filter no results */
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, py: 10, textAlign: 'center', px: 4 }}>
                  <SearchIcon sx={{ fontSize: 40, color: '#cbd5e1', mb: 1.5 }} />
                  <Typography variant="body1" fontWeight={600} color="text.secondary">
                    Sin resultados para &ldquo;{searchQuery || SPORT_FILTER_OPTS.find(o => o.value === sportFilter)?.label}&rdquo;
                  </Typography>
                  <Typography variant="body2" color="text.disabled" sx={{ mt: 0.5, mb: 2 }}>
                    Probá con otro nombre o limpiá los filtros.
                  </Typography>
                  <button
                    onClick={() => { setSearchQuery(''); setSportFilter('ALL'); setDifficultyFilter('ALL'); }}
                    style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 8, padding: '5px 14px', fontSize: 12, cursor: 'pointer', color: '#64748b' }}
                  >
                    Limpiar filtros
                  </button>
                </Box>
              ) : (
                <List disablePadding>
                  {filteredWorkouts.map((w, idx) => {
                    const sportKey = (w.discipline ?? w.sport_type ?? '').toUpperCase();
                    const dur = fmtDuration(w.estimated_duration_seconds ? Math.round(w.estimated_duration_seconds / 60) : null);
                    const distKm = w.estimated_distance_meters ? +(w.estimated_distance_meters / 1000).toFixed(2) : null;
                    const dist = distKm ? `${distKm} km` : null;
                    return (
                      <React.Fragment key={w.id}>
                        {idx > 0 && <Divider component="li" />}
                        <ListItem
                          className="group"
                          sx={{ px: 2, py: 1, '&:hover': { bgcolor: '#fafafa' }, alignItems: 'center' }}
                          disablePadding={false}
                          secondaryAction={null}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>

                            {/* Sport icon badge */}
                            <SportIconBadge sportType={sportKey} />

                            {/* Name + meta */}
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>{w.name}</span>
                                {w.difficulty && <DifficultyChip value={w.difficulty} />}
                              </div>
                              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                                {[
                                  SPORT_CONFIG[sportKey]?.label,
                                  w.session_type,
                                  (w.elevation_gain_min_m || w.elevation_gain_max_m)
                                    ? `D+ ${w.elevation_gain_min_m ?? '?'}–${w.elevation_gain_max_m ?? '?'}m`
                                    : null,
                                ].filter(Boolean).join(' · ')}
                              </div>
                            </div>

                            {/* Zone preview bar — real zone distribution from blocks */}
                            <div style={{ width: 108, flexShrink: 0 }}>
                              <ZonePreviewBar workout={w} />
                            </div>

                            {/* Duration */}
                            <div style={{ width: 80, textAlign: 'right', flexShrink: 0 }}>
                              <span style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>{dur ?? '—'}</span>
                            </div>

                            {/* Distance */}
                            <div style={{ width: 72, textAlign: 'right', flexShrink: 0 }}>
                              <span style={{ fontSize: 12, color: '#64748b' }}>{dist ?? '—'}</span>
                            </div>

                            {/* Hover actions */}
                            <div style={{ width: 100, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end', flexShrink: 0 }}>
                              <Tooltip title="Editar">
                                <IconButton size="small" onClick={() => handleEditWorkout(w.id)}
                                  sx={{ opacity: 0, '.MuiListItem-root:hover &': { opacity: 1 }, width: 28, height: 28, bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
                                  <EditIcon sx={{ fontSize: 14 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Duplicar">
                                <IconButton size="small" onClick={() => handleDuplicateWorkout(w.id)}
                                  sx={{ opacity: 0, '.MuiListItem-root:hover &': { opacity: 1 }, width: 28, height: 28, bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
                                  <DuplicateIcon sx={{ fontSize: 14 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Eliminar">
                                <IconButton size="small" onClick={() => handleDeleteWorkout(w.id)}
                                  sx={{ opacity: 0, '.MuiListItem-root:hover &': { opacity: 1 }, width: 28, height: 28, bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#fee2e2', color: '#ef4444' } }}>
                                  <DeleteIcon sx={{ fontSize: 14 }} />
                                </IconButton>
                              </Tooltip>
                            </div>

                          </div>
                        </ListItem>
                      </React.Fragment>
                    );
                  })}
                </List>
              )}
            </>
          )}
        </Paper>

      </Box>

      {/* ── New Library Dialog ── */}
      <Dialog
        open={newLibOpen}
        onClose={() => setNewLibOpen(false)}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        <DialogTitle fontWeight={700}>Nueva carpeta</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Collapse in={!!newLibError}>
            <Alert severity="error" onClose={() => setNewLibError('')}>{newLibError}</Alert>
          </Collapse>
          <TextField
            autoFocus
            label="Nombre *"
            value={newLibName}
            onChange={(e) => setNewLibName(e.target.value)}
            fullWidth
            size="small"
            placeholder="Ej: Entrenamientos de Trail, Ciclo Base…"
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreateLibrary(); }}
          />
          <TextField
            label="Descripción (opcional)"
            value={newLibDesc}
            onChange={(e) => setNewLibDesc(e.target.value)}
            fullWidth
            size="small"
            multiline
            rows={2}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={() => setNewLibOpen(false)}
            disabled={newLibSaving}
            variant="outlined"
            sx={{ borderRadius: 2 }}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleCreateLibrary}
            disabled={newLibSaving}
            variant="contained"
            sx={{
              borderRadius: 2,
              minWidth: 100,
              bgcolor: '#f59e0b',
              '&:hover': { bgcolor: '#d97706' },
              '&.Mui-disabled': { bgcolor: '#fed7aa' },
            }}
          >
            {newLibSaving ? <CircularProgress size={18} color="inherit" /> : 'Crear'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Workout Builder Dialog ── */}
      <WorkoutBuilder
        open={builderOpen}
        onClose={() => { setBuilderOpen(false); setEditWorkout(null); }}
        orgId={orgId}
        libraryId={selectedLibId}
        onSaved={handleWorkoutSaved}
        editWorkout={editWorkout}
        onUpdated={handleWorkoutUpdated}
      />

      {/* ── Snackbar ── */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={3500}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={snackbar.severity}
          variant="filled"
          onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        >
          {snackbar.msg}
        </Alert>
      </Snackbar>
    </Layout>
  );
}
