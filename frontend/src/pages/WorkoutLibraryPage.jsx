import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Button, IconButton, Chip, CircularProgress, Alert, Divider, Collapse,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  List, ListItem, ListItemText, ListItemSecondaryAction, ListItemButton,
  Tooltip, Snackbar, Skeleton,
  Menu, MenuItem as MuiMenuItem,
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

const SPORT_LABELS = {
  TRAIL: 'Trail', RUN: 'Running', BIKE: 'Ciclismo',
  WALK: 'Caminata', STRENGTH: 'Fuerza', OTHER: 'Otro',
};

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

  // ── Action menu per workout ──────────────────────────────────────────────────
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [menuWorkoutId, setMenuWorkoutId] = useState(null);
  const openMenu = (e, workoutId) => { e.stopPropagation(); setMenuAnchor(e.currentTarget); setMenuWorkoutId(workoutId); };
  const closeMenu = () => { setMenuAnchor(null); setMenuWorkoutId(null); };

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
    closeMenu();
    try {
      const res = await getPlannedWorkout(orgId, selectedLibId, workoutId);
      setEditWorkout(res.data);
      setBuilderOpen(true);
    } catch {
      toast('No se pudo cargar el entrenamiento para editar.', 'error');
    }
  };

  const handleDuplicateWorkout = async (workoutId) => {
    closeMenu();
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
  };

  // ── Selected library object ─────────────────────────────────────────────────
  const selectedLib = libraries.find((l) => l.id === selectedLibId);

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
              {/* Panel header */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 3, py: 1.5, borderBottom: '1px solid', borderColor: 'grey.100' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                  <FolderOpenIcon sx={{ color: '#f59e0b', fontSize: 18, flexShrink: 0 }} />
                  <Typography variant="body2" fontWeight={700} noWrap color="text.primary">
                    {selectedLib?.name}
                  </Typography>
                  <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                    · {workouts.length} entrenamiento{workouts.length !== 1 ? 's' : ''}
                  </Typography>
                </Box>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={() => { setEditWorkout(null); setBuilderOpen(true); }}
                  sx={{
                    borderRadius: 1.5,
                    bgcolor: '#f59e0b',
                    '&:hover': { bgcolor: '#d97706' },
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.8rem',
                    flexShrink: 0,
                    ml: 2,
                    boxShadow: 'none',
                  }}
                >
                  Nuevo entrenamiento
                </Button>
              </Box>

              {/* Column headers */}
              {!workoutsLoading && workouts.length > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', px: 3, py: 1, borderBottom: '1px solid', borderColor: 'grey.100', bgcolor: 'grey.50' }}>
                  <Typography variant="caption" sx={{ flex: 1, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, color: 'text.disabled' }}>
                    Entrenamiento
                  </Typography>
                  <Typography variant="caption" sx={{ width: 96, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, color: 'text.disabled', textAlign: 'right' }}>
                    Duración
                  </Typography>
                  <Typography variant="caption" sx={{ width: 96, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, color: 'text.disabled', textAlign: 'right' }}>
                    Distancia
                  </Typography>
                  <Box sx={{ width: 32 }} />
                </Box>
              )}

              {/* Workout rows */}
              {workoutsLoading ? (
                <Box sx={{ px: 3, py: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} variant="rounded" height={52} />
                  ))}
                </Box>
              ) : workouts.length === 0 ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, py: 10, textAlign: 'center', px: 4 }}>
                  <Dumbbell className="w-12 h-12 mb-4" style={{ color: '#cbd5e1' }} />
                  <Typography variant="h6" fontWeight={600} color="text.secondary" gutterBottom>
                    Carpeta vacía
                  </Typography>
                  <Typography variant="body2" color="text.disabled" sx={{ mb: 3 }}>
                    Agrega el primer entrenamiento a esta librería para empezar a asignarlo en el calendario.
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
              ) : (
                <List disablePadding>
                  {workouts.map((w, idx) => (
                    <React.Fragment key={w.id}>
                      {idx > 0 && <Divider component="li" />}
                      <ListItem
                        sx={{ px: 3, py: 1.25, '&:hover': { bgcolor: 'grey.50' } }}
                        secondaryAction={
                          <Tooltip title="Acciones">
                            <IconButton edge="end" size="small" onClick={(e) => openMenu(e, w.id)}>
                              <MoreVertIcon fontSize="small" sx={{ color: 'text.disabled' }} />
                            </IconButton>
                          </Tooltip>
                        }
                      >
                        <div className="flex items-center gap-3 flex-1 min-w-0 pr-4">
                          {/* Name + badges */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-semibold text-slate-900 truncate">
                                {w.name}
                              </span>
                              {w.sport_type && (
                                <span className="px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 rounded border border-slate-200 flex-shrink-0">
                                  {SPORT_LABELS[w.sport_type] ?? w.sport_type}
                                </span>
                              )}
                              {w.difficulty && <DifficultyChip value={w.difficulty} />}
                            </div>
                            {w.description && (
                              <p className="text-xs text-slate-400 mt-0.5 truncate max-w-md">
                                {w.description}
                              </p>
                            )}
                          </div>

                          {/* Duration */}
                          <span className="w-24 text-xs text-slate-500 text-right flex-shrink-0">
                            {w.estimated_duration_minutes ? `${w.estimated_duration_minutes} min` : '—'}
                          </span>

                          {/* Distance */}
                          <span className="w-24 text-xs text-slate-500 text-right flex-shrink-0">
                            {w.estimated_distance_km ? `${w.estimated_distance_km} km` : '—'}
                          </span>
                        </div>
                      </ListItem>
                    </React.Fragment>
                  ))}
                </List>
              )}
            </>
          )}
        </Paper>

      </Box>

      {/* ── Workout Action Menu ── */}
      <Menu
        anchorEl={menuAnchor}
        open={!!menuAnchor}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{ sx: { borderRadius: 2, minWidth: 160 } }}
      >
        <MuiMenuItem onClick={() => handleEditWorkout(menuWorkoutId)}>
          <EditIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
          Editar
        </MuiMenuItem>
        <MuiMenuItem onClick={() => handleDuplicateWorkout(menuWorkoutId)}>
          <DuplicateIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
          Duplicar
        </MuiMenuItem>
        <MuiMenuItem
          onClick={() => { closeMenu(); handleDeleteWorkout(menuWorkoutId); }}
          sx={{ color: '#ef4444' }}
        >
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
          Eliminar
        </MuiMenuItem>
      </Menu>

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
