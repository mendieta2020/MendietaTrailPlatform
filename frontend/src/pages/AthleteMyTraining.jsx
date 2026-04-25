import React, { useState, useEffect, useCallback } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  Box, Typography, CircularProgress, Alert, Button,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Grid, FormControl, InputLabel, Select, MenuItem as MuiMenuItem,
} from '@mui/material';
import {
  startOfMonth, endOfMonth, startOfWeek, format,
} from 'date-fns';
import AthleteLayout from '../components/AthleteLayout';
import WorkoutModal from '../components/calendar/WorkoutModal';
import { CompleteWorkoutModal } from '../components/CompleteWorkoutModal';
import VisibilityGate from '../components/VisibilityGate';
import { useAuth } from '../context/AuthContext';
import { listAssignments, updateAssignment, getCalendarTimeline } from '../api/assignments';
import { listAthletes, getAthleteProfile } from '../api/p1';
import { getAthleteGoals } from '../api/pmc';
import { getAvailability, updateGoal } from '../api/athlete';
import { getPlanVsReal } from '../api/planning';
import client from '../api/client';
import CalendarGrid from '../components/calendar/CalendarGrid';

// ── Helpers now in calendarHelpers.js (shared) ───────────────────────────────


// ── PR-161: Athlete goal edit dialog ─────────────────────────────────────────

function AthleteGoalEditDialog({ goal, orgId, onClose, onSaved }) {
  const [form, setForm] = React.useState({
    title:                  goal.title ?? '',
    target_date:            goal.target_date ?? '',
    priority:               goal.priority ?? 'B',
    status:                 goal.status ?? 'active',
    target_distance_km:     goal.target_distance_km ?? '',
    target_elevation_gain_m: goal.target_elevation_gain_m ?? '',
  });
  const [saving, setSaving] = React.useState(false);
  const [error,  setError]  = React.useState(null);

  const handleSave = async () => {
    if (!orgId || !goal.id) return;
    setSaving(true);
    try {
      const patch = {
        title:    form.title,
        priority: form.priority,
        status:   form.status,
        target_date: form.target_date || null,
        target_distance_km:      form.target_distance_km === '' ? null : Number(form.target_distance_km),
        target_elevation_gain_m: form.target_elevation_gain_m === '' ? null : Number(form.target_elevation_gain_m),
      };
      const { data: updated } = await updateGoal(orgId, goal.id, patch);
      onSaved(updated);
    } catch {
      setError('No se pudo guardar el objetivo.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700, fontSize: '1rem' }}>🏆 Editar Objetivo</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
        <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
          <Grid item xs={12}>
            <TextField label="Nombre" size="small" fullWidth value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          </Grid>
          <Grid item xs={12}>
            <TextField label="Fecha objetivo" type="date" size="small" fullWidth InputLabelProps={{ shrink: true }} value={form.target_date} onChange={e => setForm(f => ({ ...f, target_date: e.target.value }))} />
          </Grid>
          <Grid item xs={6}>
            <FormControl size="small" fullWidth>
              <InputLabel>Prioridad</InputLabel>
              <Select label="Prioridad" value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                <MuiMenuItem value="A">A — Principal</MuiMenuItem>
                <MuiMenuItem value="B">B — Secundario</MuiMenuItem>
                <MuiMenuItem value="C">C — Desarrollo</MuiMenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6}>
            <FormControl size="small" fullWidth>
              <InputLabel>Estado</InputLabel>
              <Select label="Estado" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                <MuiMenuItem value="active">Activo</MuiMenuItem>
                <MuiMenuItem value="completed">Completado</MuiMenuItem>
                <MuiMenuItem value="cancelled">Cancelado</MuiMenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6}>
            <TextField label="Distancia (km)" type="number" size="small" fullWidth value={form.target_distance_km} onChange={e => setForm(f => ({ ...f, target_distance_km: e.target.value }))} />
          </Grid>
          <Grid item xs={6}>
            <TextField label="Elevación (m)" type="number" size="small" fullWidth value={form.target_elevation_gain_m} onChange={e => setForm(f => ({ ...f, target_elevation_gain_m: e.target.value }))} />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button variant="text" onClick={onClose} sx={{ textTransform: 'none', color: '#64748B' }}>Cancelar</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          sx={{ textTransform: 'none', bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00BF99' } }}
        >
          {saving ? <CircularProgress size={14} sx={{ color: '#fff' }} /> : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

const AthleteMyTraining = () => {
  const { user } = useAuth();
  const location = useLocation();
  const orgId = user?.memberships?.[0]?.org_id;

  const [currentDate, setCurrentDate] = useState(new Date());
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pmcData, setPmcData] = useState(null);
  // Deep-link from MessagesDrawer: opens WorkoutModal for a specific assignment
  const [deepLinkAssignment, setDeepLinkAssignment] = useState(null);
  const [completeModalOpen, setCompleteModalOpen] = useState(false);
  const [completeTarget, setCompleteTarget] = useState(null);
  // availability: array of { day_of_week, is_available, reason }
  const [availability, setAvailability] = useState([]);
  // PR-155: athlete profile for menstrual cycle overlay
  const [athleteProfile, setAthleteProfile] = useState(null);
  // PR-157 hotfix / PR-161: athlete goals for race date badges + editing
  const [goalDateMap, setGoalDateMap] = useState({}); // { 'YYYY-MM-DD': { title, distance, elevation, id, priority, status, target_date } }
  const [selectedGoalForEdit, setSelectedGoalForEdit] = useState(null);
  // PR-158: plan vs real data keyed by week Monday string
  const [planVsRealMap, setPlanVsRealMap] = useState({}); // { 'YYYY-MM-DD': {...} }
  // PR-179a: calendar timeline — completed activities + reconciliation map
  const [calActivities, setCalActivities] = useState([]);
  const [calReconciliationMap, setCalReconciliationMap] = useState({});
  // PR-179b: enriched plan details map { [assignmentId]: planEntry }
  const [calPlanDetailsMap, setCalPlanDetailsMap] = useState({});

  const fetchData = useCallback(async () => {
    if (!orgId) { setLoading(false); return; }
    setLoading(true);
    setError('');
    try {
      const dateFrom = format(startOfMonth(currentDate), 'yyyy-MM-dd');
      const dateTo = format(endOfMonth(currentDate), 'yyyy-MM-dd');
      const [res, timelineRes] = await Promise.all([
        listAssignments(orgId, { dateFrom, dateTo }),
        getCalendarTimeline(orgId, { startDate: dateFrom, endDate: dateTo }).catch(() => null),
      ]);
      const data = res.data?.results ?? res.data ?? [];
      setAssignments(Array.isArray(data) ? data : []);
      const acts = timelineRes?.data?.activities ?? [];
      setCalActivities(acts);
      const recMap = {};
      for (const r of (timelineRes?.data?.reconciliations ?? [])) recMap[r.plan_id] = r;
      setCalReconciliationMap(recMap);
      const pdMap = {};
      for (const p of (timelineRes?.data?.plans ?? [])) pdMap[p.id] = p;
      setCalPlanDetailsMap(pdMap);
      // Diagnostic: warn when upcoming assignments (within ±4-day enrichment window) have no weather
      if (timelineRes?.data?.plans) {
        const today = new Date();
        const windowMs = 4 * 24 * 60 * 60 * 1000;
        const missing = timelineRes.data.plans.filter((p) => {
          if (p.weather) return false;
          const d = new Date(p.date + 'T00:00:00');
          return Math.abs(d - today) <= windowMs;
        });
        if (missing.length > 0) {
          console.warn('[AthleteMyTraining] weather_snapshot missing for upcoming assignments', {
            event_name: 'weather_snapshot_missing',
            count: missing.length,
            assignment_ids: missing.map((p) => p.id),
          });
        }
      }
    } catch (err) {
      // 403 + paywall: VisibilityGate handles the overlay — no error toast needed
      const isPaywall = err?.response?.status === 403 && err?.response?.data?.paywall === true;
      if (!isPaywall) {
        setError('Error cargando el calendario. Intenta de nuevo.');
      }
      console.error('[AthleteMyTraining] fetch assignments error:', err);
    } finally {
      setLoading(false);
    }
  }, [orgId, currentDate]);

  // Fetch athlete availability + profile once on mount
  useEffect(() => {
    if (!orgId || !user?.id) return;
    listAthletes(orgId)
      .then((res) => {
        const athletes = res.data?.results ?? res.data ?? [];
        const me = athletes.find((a) => String(a.user_id) === String(user.id));
        const target = me || (athletes.length > 0 ? athletes[0] : null);
        if (!target) return null;
        return Promise.all([
          getAvailability(orgId, target.id),
          getAthleteProfile(orgId, target.id).catch(() => ({ data: null })),
        ]);
      })
      .then((results) => {
        if (!results) return;
        const [availRes, profileRes] = results;
        if (availRes?.data) {
          const avail = Array.isArray(availRes.data) ? availRes.data : availRes.data?.results ?? [];
          setAvailability(avail);
        }
        if (profileRes?.data) setAthleteProfile(profileRes.data);
      })
      .catch((err) => {
        console.warn('[AthleteMyTraining] availability/profile fetch failed:', err);
      });
  }, [orgId, user?.id]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Deep-link from MessagesDrawer:
  // Step 1 (mount-only) — navigate to the right month so the correct data is fetched.
  // Step 2 (data-watch) — once assignments load, find and open the target drawer.
  // Both setState calls are conditional one-shots; they cannot loop.
  useEffect(() => {
    const assignmentDate = sessionStorage.getItem('openAssignmentDate');
    if (!assignmentDate) return;
    const targetDate = new Date(assignmentDate + 'T00:00:00');
    sessionStorage.removeItem('openAssignmentDate');
    setCurrentDate(targetDate);
  }, []); // intentionally mount-only

  useEffect(() => {
    const assignmentId = sessionStorage.getItem('openAssignmentId');
    if (!assignmentId || loading || assignments.length === 0) return;
    const targetId = parseInt(assignmentId, 10);
    const found = assignments.find((a) => a.id === targetId);
    if (found) {
      sessionStorage.removeItem('openAssignmentId');
      setDeepLinkAssignment(found);
    }
  }, [assignments, loading]);

  // Cleanup stale deep-link keys on unmount to prevent cross-session leakage.
  useEffect(() => {
    return () => {
      sessionStorage.removeItem('openAssignmentId');
      sessionStorage.removeItem('openAssignmentDate');
    };
  }, []);

  // Same-route deep-link: fires when already on /athlete/training and "Ver sesión" is clicked.
  // AthleteLayout passes { state: { _deepLinkAt: Date.now() } } so location.state changes
  // even for same-route navigation, triggering this effect without a component remount.
  useEffect(() => {
    if (!location.state?._deepLinkAt) return;
    const assignmentDate = sessionStorage.getItem('openAssignmentDate');
    if (assignmentDate) {
      const targetDate = new Date(assignmentDate + 'T00:00:00');
      sessionStorage.removeItem('openAssignmentDate');
      setCurrentDate(targetDate);
    }
    // Always re-fetch so the data-watch effect can pick up openAssignmentId even when
    // the target month is already displayed (setCurrentDate would be a React no-op in that case).
    fetchData();
  }, [location.state?._deepLinkAt]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    client.get('/api/athlete/pmc/')
      .then((res) => setPmcData(res.data))
      .catch(() => setPmcData(null));
  }, []);

  // PR-157 hotfix / PR-160 / PR-161: load athlete goals for race date badges + editing
  useEffect(() => {
    let cancelled = false;
    getAthleteGoals()
      .then((res) => {
        if (!cancelled) {
          const map = {};
          (res.data?.goals ?? []).forEach((g) => {
            const dateKey = g.date || g.target_date;
            if (dateKey) {
              map[dateKey] = {
                id:        g.id,
                title:     g.name || g.title || '',
                distance:  g.target_distance_km ?? null,
                elevation: g.target_elevation_gain_m ?? null,
                priority:  g.priority ?? 'B',
                status:    g.status ?? 'active',
                target_date: g.target_date ?? dateKey,
                target_distance_km:      g.target_distance_km ?? null,
                target_elevation_gain_m: g.target_elevation_gain_m ?? null,
              };
            }
          });
          setGoalDateMap(map);
        }
      })
      .catch(() => { if (!cancelled) setGoalDateMap({}); });
    return () => { cancelled = true; };
  }, []);

  // PR-158: Load Plan vs Real for visible weeks
  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    const monthStart = startOfMonth(currentDate);
    const calStart = startOfWeek(monthStart, { weekStartsOn: 1 });
    // Collect all Mondays visible in this month view
    const mondays = [];
    let d = calStart;
    while (d <= endOfMonth(currentDate)) {
      mondays.push(format(d, 'yyyy-MM-dd'));
      d = new Date(d);
      d.setDate(d.getDate() + 7);
    }
    Promise.all(
      mondays.map((wk) =>
        getPlanVsReal({ weekStart: wk })
          .then((res) => ({ wk, data: res.data }))
          .catch(() => ({ wk, data: null }))
      )
    ).then((results) => {
      if (cancelled) return;
      const map = {};
      results.forEach(({ wk, data }) => { if (data) map[wk] = data; });
      setPlanVsRealMap(map);
    });
    return () => { cancelled = true; };
  }, [orgId, currentDate]);


  const handleOpenCompleteModal = (assignment) => {
    setCompleteTarget(assignment);
    setCompleteModalOpen(true);
  };

  const handleCompleteSubmit = async (data) => {
    if (!orgId || !completeTarget) return;
    const res = await updateAssignment(orgId, completeTarget.id, data);
    setAssignments((prev) => prev.map((a) => a.id === completeTarget.id ? res.data : a));
    if (deepLinkAssignment?.id === completeTarget.id) {
      setDeepLinkAssignment(res.data);
    }
  };

  const role = user?.memberships?.[0]?.role;
  if (role && role !== 'athlete') {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <AthleteLayout user={user}>
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Mi Entrenamiento</Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>Calendario de sesiones asignadas</Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

      {/* PR-168a: Gate — cancelled/trial_expired/none get paywall; paused gets read-only */}
      <VisibilityGate requiredAccess="limited" pausedLabel="⏸️ Suscripción pausada — solo lectura">

      {/* PR-163 QA Fix 8: always render CalendarGrid — navigating to empty months must show the grid, not crash */}
      <CalendarGrid
        assignments={assignments}
        goalDateMap={goalDateMap}
        planVsRealMap={planVsRealMap}
        pmcData={pmcData}
        trainingPhaseMap={{}}
        role="athlete"
        currentDate={currentDate}
        onNavigate={setCurrentDate}
        loading={loading}
        onCompleteClick={handleOpenCompleteModal}
        availability={availability}
        athleteProfile={athleteProfile}
        onGoalClick={(goal) => setSelectedGoalForEdit(goal)}
        activities={calActivities}
        reconciliationMap={calReconciliationMap}
        planDetailsMap={calPlanDetailsMap}
      />

      {/* Deep-link WorkoutModal (opened from MessagesDrawer notification) */}
      <WorkoutModal
        open={!!deepLinkAssignment}
        onClose={() => setDeepLinkAssignment(null)}
        payload={deepLinkAssignment ? {
          assignment: deepLinkAssignment,
          activity: calActivities.find((a) => a.linked_plan_id === deepLinkAssignment.id) ?? null,
          reconciliation: calReconciliationMap[deepLinkAssignment.id] ?? null,
          planDetails: calPlanDetailsMap[deepLinkAssignment.id] ?? null,
          freeActivity: null,
        } : null}
        role="athlete"
      />

      {/* Complete workout modal */}
      <CompleteWorkoutModal
        open={completeModalOpen}
        onClose={() => { setCompleteModalOpen(false); setCompleteTarget(null); }}
        onSubmit={handleCompleteSubmit}
        assignment={completeTarget}
      />

      {/* PR-161: Goal edit dialog */}
      {selectedGoalForEdit && (
        <AthleteGoalEditDialog
          goal={selectedGoalForEdit}
          orgId={orgId}
          onClose={() => setSelectedGoalForEdit(null)}
          onSaved={(updated) => {
            const dateKey = updated.target_date;
            setGoalDateMap(prev => {
              const newMap = { ...prev };
              // Remove old entry if date changed
              Object.keys(newMap).forEach(k => {
                if (newMap[k].id === updated.id) delete newMap[k];
              });
              if (dateKey) {
                newMap[dateKey] = {
                  id:        updated.id,
                  title:     updated.title ?? '',
                  distance:  updated.target_distance_km ?? null,
                  elevation: updated.target_elevation_gain_m ?? null,
                  priority:  updated.priority ?? 'B',
                  status:    updated.status ?? 'active',
                  target_date: dateKey,
                  target_distance_km:      updated.target_distance_km ?? null,
                  target_elevation_gain_m: updated.target_elevation_gain_m ?? null,
                };
              }
              return newMap;
            });
            setSelectedGoalForEdit(null);
          }}
        />
      )}
      </VisibilityGate>
    </AthleteLayout>
  );
};

export default AthleteMyTraining;
