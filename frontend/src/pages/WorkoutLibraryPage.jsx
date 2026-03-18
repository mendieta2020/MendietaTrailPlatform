import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Button, Paper, Grid, Card, CardContent, CardActions,
  IconButton, Chip, CircularProgress, Alert, Divider, Collapse,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  List, ListItem, ListItemText, ListItemSecondaryAction, Tooltip, Snackbar,
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
  DirectionsRun as RunIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  LibraryBooks as LibraryBooksIcon,
} from '@mui/icons-material';
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
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
          <CircularProgress />
        </Box>
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
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <LibraryBooksIcon sx={{ color: '#F57C00' }} />
            <Typography variant="h5" fontWeight={700}>Librería de Entrenamientos</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            {activeOrg.org_name} · Diseña y organiza tus rutinas estructuradas
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setNewLibOpen(true)}
          sx={{ borderRadius: 2 }}
        >
          Nueva librería
        </Button>
      </Box>

      {libError && <Alert severity="error" sx={{ mb: 2 }}>{libError}</Alert>}

      {/* ── Libraries Grid ── */}
      {libLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress />
        </Box>
      ) : libraries.length === 0 ? (
        <Paper
          variant="outlined"
          sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8, borderRadius: 3, borderStyle: 'dashed' }}
        >
          <FolderOpenIcon sx={{ fontSize: 56, color: '#cbd5e1', mb: 2 }} />
          <Typography variant="h6" color="text.secondary" fontWeight={600}>Sin librerías</Typography>
          <Typography variant="body2" color="text.disabled" sx={{ mb: 3 }}>
            Crea tu primera librería para organizar tus entrenamientos.
          </Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setNewLibOpen(true)} sx={{ borderRadius: 2 }}>
            Crear librería
          </Button>
        </Paper>
      ) : (
        <Grid container spacing={2}>
          {libraries.map((lib) => {
            const isSelected = selectedLibId === lib.id;
            return (
              <Grid key={lib.id} item xs={12} sm={6} md={4}>
                <Card
                  sx={{
                    borderRadius: 3,
                    cursor: 'pointer',
                    border: '2px solid',
                    borderColor: isSelected ? '#F57C00' : 'transparent',
                    boxShadow: isSelected ? '0 0 0 1px #F57C00' : undefined,
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                    '&:hover': { borderColor: '#F57C00', boxShadow: '0 0 0 1px #F57C00' },
                  }}
                  onClick={() => handleToggleLibrary(lib.id)}
                >
                  <CardContent sx={{ pb: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <FolderOpenIcon sx={{ color: '#F57C00', fontSize: 22 }} />
                        <Typography variant="subtitle1" fontWeight={700} noWrap>{lib.name}</Typography>
                      </Box>
                      <Tooltip title="Eliminar librería">
                        <IconButton
                          size="small"
                          onClick={(e) => { e.stopPropagation(); handleDeleteLibrary(lib.id); }}
                        >
                          <DeleteIcon fontSize="small" sx={{ color: '#ef4444' }} />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    {lib.description && (
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {lib.description}
                      </Typography>
                    )}
                  </CardContent>
                  <CardActions sx={{ px: 2, pt: 0, pb: 1.5, justifyContent: 'space-between' }}>
                    <Chip
                      icon={<FitnessCenterIcon sx={{ fontSize: '14px !important' }} />}
                      label={`${lib.workout_count ?? '—'} entrenamientos`}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.7rem' }}
                    />
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: isSelected ? '#F57C00' : 'text.secondary' }}>
                      <Typography variant="caption" fontWeight={600}>{isSelected ? 'Ocultar' : 'Ver'}</Typography>
                      {isSelected ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                    </Box>
                  </CardActions>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* ── Workout List (expanded panel) ── */}
      <Collapse in={!!selectedLibId} unmountOnExit>
        <Paper variant="outlined" sx={{ mt: 3, borderRadius: 3, overflow: 'hidden' }}>
          {/* Panel header */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 3, py: 2, bgcolor: '#F57C0008' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <FolderOpenIcon sx={{ color: '#F57C00' }} />
              <Box>
                <Typography variant="subtitle1" fontWeight={700}>{selectedLib?.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {workouts.length} entrenamiento{workouts.length !== 1 ? 's' : ''}
                </Typography>
              </Box>
            </Box>
            <Button
              variant="contained"
              size="small"
              startIcon={<AddIcon />}
              onClick={() => { setEditWorkout(null); setBuilderOpen(true); }}
              sx={{ borderRadius: 2 }}
            >
              Nuevo entrenamiento
            </Button>
          </Box>

          <Divider />

          {/* Workout list */}
          {workoutsLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          ) : workouts.length === 0 ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 6 }}>
              <RunIcon sx={{ fontSize: 40, color: '#cbd5e1', mb: 1 }} />
              <Typography variant="body2" color="text.secondary">Esta librería no tiene entrenamientos todavía.</Typography>
              <Button
                variant="outlined"
                startIcon={<AddIcon />}
                size="small"
                onClick={() => { setEditWorkout(null); setBuilderOpen(true); }}
                sx={{ mt: 2, borderRadius: 2 }}
              >
                Crear el primero
              </Button>
            </Box>
          ) : (
            <List disablePadding>
              {workouts.map((w, idx) => (
                <React.Fragment key={w.id}>
                  {idx > 0 && <Divider component="li" />}
                  <ListItem sx={{ px: 3, py: 1.5, '&:hover': { bgcolor: '#f8fafc' } }}>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                          <Typography variant="body1" fontWeight={600}>{w.name}</Typography>
                          {w.sport_type && (
                            <Chip label={SPORT_LABELS[w.sport_type] ?? w.sport_type} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
                          )}
                          {w.difficulty && <DifficultyChip value={w.difficulty} />}
                        </Box>
                      }
                      secondary={
                        <Box sx={{ display: 'flex', gap: 2, mt: 0.5, flexWrap: 'wrap' }}>
                          {w.estimated_duration_minutes && (
                            <Typography variant="caption" color="text.secondary">
                              ⏱ {w.estimated_duration_minutes} min
                            </Typography>
                          )}
                          {w.estimated_distance_km && (
                            <Typography variant="caption" color="text.secondary">
                              📍 {w.estimated_distance_km} km
                            </Typography>
                          )}
                          {w.description && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden', maxWidth: 400 }}>
                              {w.description}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <Tooltip title="Acciones">
                        <IconButton edge="end" size="small" onClick={(e) => openMenu(e, w.id)}>
                          <MoreVertIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </ListItemSecondaryAction>
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
          )}
        </Paper>
      </Collapse>

      {/* ── Workout Action Menu ── */}
      <Menu
        anchorEl={menuAnchor}
        open={!!menuAnchor}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
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
      <Dialog open={newLibOpen} onClose={() => setNewLibOpen(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle fontWeight={700}>Nueva librería</DialogTitle>
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
          <Button onClick={() => setNewLibOpen(false)} disabled={newLibSaving} variant="outlined" sx={{ borderRadius: 2 }}>
            Cancelar
          </Button>
          <Button onClick={handleCreateLibrary} disabled={newLibSaving} variant="contained" sx={{ borderRadius: 2, minWidth: 100 }}>
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
        <Alert severity={snackbar.severity} variant="filled" onClose={() => setSnackbar((s) => ({ ...s, open: false }))}>
          {snackbar.msg}
        </Alert>
      </Snackbar>
    </Layout>
  );
}
