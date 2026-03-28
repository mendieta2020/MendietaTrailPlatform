/**
 * Plantilla.jsx — PR-145h
 *
 * Vista "Plantilla de Entrenamiento": tabla multi-atleta semanal con:
 * - Selector de equipo
 * - Navegación semana lunes→domingo
 * - Grid de compliance (dots verdes/amarillo/rojo/azul/gris)
 * - Drag & drop desde librería → bulk assign
 * - Click en dot → WorkoutCoachDrawer
 * - Click en atleta → navigate /calendar (con sessionStorage)
 * - Checkboxes por fila + seleccionar todos
 */

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useReducer,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  Checkbox,
  Tooltip,
  Snackbar,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
} from '@mui/material';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import {
  ChevronLeft,
  ChevronRight,
  Today,
  FitnessCenter,
  ExpandMore,
  MenuOpen as MenuOpenIcon,
  Menu as MenuIcon,
} from '@mui/icons-material';
import { BookOpen } from 'lucide-react';
import Layout from '../components/Layout';
import WorkoutCoachDrawer from '../components/WorkoutCoachDrawer';
import { useOrg } from '../context/OrgContext';
import { getTeams, getComplianceWeek } from '../api/teams';
import { listLibraries, listPlannedWorkouts } from '../api/p1';
import { bulkCreateAssignments, getAssignment } from '../api/assignments';
import { getAthleteAlerts, sendMessage } from '../api/messages';

// ── Constants ─────────────────────────────────────────────────────────────────

const DOT_COLOR = {
  green:  '#22C55E',
  yellow: '#EAB308',
  red:    '#EF4444',
  blue:   '#3B82F6',
  gray:   '#64748B',
};

const DOT_LABEL = {
  green:  'Completado ≥90%',
  yellow: 'Completado 70-89%',
  red:    'Completado <70%',
  blue:   'Sobrecarga ≥120%',
  gray:   'Planificado',
};

const DAY_LABELS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

// ── Helpers ──────────────────────────────────────────────────────────────────

function getMondayOf(date) {
  const d = new Date(date);
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d;
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function toISO(date) {
  return date.toISOString().slice(0, 10);
}

function formatWeekLabel(monday) {
  const sunday = addDays(monday, 6);
  const opts = { day: 'numeric', month: 'short' };
  return `${monday.toLocaleDateString('es-AR', opts)} – ${sunday.toLocaleDateString('es-AR', opts)}`;
}

// ── fetchReducer ──────────────────────────────────────────────────────────────

function fetchReducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':  return { ...state, loading: true, error: null };
    case 'FETCH_SUCCESS': return { data: action.data, loading: false, error: null };
    case 'FETCH_ERROR':  return { ...state, loading: false, error: action.error };
    default: return state;
  }
}

// ── WorkoutCard (draggable from library) ─────────────────────────────────────

function WorkoutCard({ workout, onDragStart, onDragEnd }) {
  const [dragging, setDragging] = useState(false);
  return (
    <Box
      draggable
      onDragStart={(e) => { e.dataTransfer.effectAllowed = 'copy'; onDragStart(workout); setDragging(true); }}
      onDragEnd={() => { onDragEnd(); setDragging(false); }}
      sx={{
        p: 1.5, mb: 0.75, borderRadius: 1.5,
        bgcolor: dragging ? 'rgba(245,124,0,0.12)' : '#1c2230',
        border: '1px solid',
        borderColor: dragging ? '#F57C00' : 'rgba(255,255,255,0.07)',
        cursor: 'grab', opacity: dragging ? 0.45 : 1,
        '&:hover': { borderColor: '#F57C00', bgcolor: 'rgba(245,124,0,0.07)' },
      }}
    >
      <Typography variant="caption" sx={{ color: '#F57C00', fontWeight: 600, display: 'block', lineHeight: 1 }}>
        <FitnessCenter sx={{ fontSize: 10, mr: 0.5, verticalAlign: 'middle' }} />
        arrastrar
      </Typography>
      <Typography variant="body2" sx={{ color: '#e2e8f0', fontWeight: 500, mt: 0.4 }} noWrap>
        {workout.name}
      </Typography>
    </Box>
  );
}

// ── LibrarySidebar ────────────────────────────────────────────────────────────

function LibrarySidebar({ orgId, onDragStart, onDragEnd, collapsed, onToggle }) {
  const [libState, libDispatch] = useReducer(fetchReducer, { data: [], loading: false, error: null });
  const [workoutsByLib, setWorkoutsByLib] = useState({});
  const [loadingWorkouts, setLoadingWorkouts] = useState({});

  useEffect(() => {
    if (!orgId) return;
    libDispatch({ type: 'FETCH_START' });
    listLibraries(orgId)
      .then((res) => libDispatch({ type: 'FETCH_SUCCESS', data: res.data?.results ?? res.data ?? [] }))
      .catch(() => libDispatch({ type: 'FETCH_ERROR', error: 'Error cargando librerías.' }));
  }, [orgId]);

  const handleExpand = useCallback((libId) => {
    if (workoutsByLib[libId] !== undefined) return;
    setLoadingWorkouts((p) => ({ ...p, [libId]: true }));
    listPlannedWorkouts(orgId, libId)
      .then((res) => setWorkoutsByLib((p) => ({ ...p, [libId]: res.data?.results ?? res.data ?? [] })))
      .finally(() => setLoadingWorkouts((p) => ({ ...p, [libId]: false })));
  }, [orgId, workoutsByLib]);

  return (
    <Box sx={{
      width: collapsed ? 48 : 240,
      minWidth: collapsed ? 48 : 240,
      bgcolor: '#111827',
      borderLeft: '1px solid rgba(255,255,255,0.07)',
      display: 'flex', flexDirection: 'column',
      transition: 'width 0.2s',
      overflow: 'hidden',
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', p: 1, borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <IconButton size="small" onClick={onToggle} sx={{ color: '#94a3b8' }}>
          {collapsed ? <MenuIcon fontSize="small" /> : <MenuOpenIcon fontSize="small" />}
        </IconButton>
        {!collapsed && (
          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, ml: 1, letterSpacing: 1, textTransform: 'uppercase' }}>
            Librería
          </Typography>
        )}
      </Box>

      {!collapsed && (
        <Box sx={{ flex: 1, overflowY: 'auto', p: 1 }}>
          {libState.loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <CircularProgress size={20} sx={{ color: '#F57C00' }} />
            </Box>
          )}
          {!libState.loading && !libState.data.length && (
            <Box sx={{ textAlign: 'center', py: 4, px: 1 }}>
              <BookOpen style={{ width: 24, height: 24, color: '#4a5568', marginBottom: 8 }} />
              <Typography variant="caption" sx={{ color: '#4a5568', display: 'block' }}>
                Sin librerías
              </Typography>
            </Box>
          )}
          {libState.data.map((lib) => (
            <Accordion
              key={lib.id} disableGutters elevation={0}
              onChange={(_, expanded) => { if (expanded) handleExpand(lib.id); }}
              sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}
            >
              <AccordionSummary
                expandIcon={<ExpandMore sx={{ color: '#64748b', fontSize: 16 }} />}
                sx={{ px: 0.5, py: 0.5, minHeight: 32 }}
              >
                <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600, fontSize: '0.7rem' }} noWrap>
                  {lib.name}
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ p: 0, pl: 0.5 }}>
                {loadingWorkouts[lib.id] && (
                  <CircularProgress size={14} sx={{ color: '#F57C00', m: 1 }} />
                )}
                {(workoutsByLib[lib.id] ?? []).map((w) => (
                  <WorkoutCard key={w.id} workout={w} onDragStart={onDragStart} onDragEnd={onDragEnd} />
                ))}
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}
    </Box>
  );
}

// ── ComplianceDot ─────────────────────────────────────────────────────────────

function ComplianceDot({ color, onClick }) {
  return (
    <Tooltip title={DOT_LABEL[color] ?? color} placement="top">
      <Box
        onClick={onClick}
        sx={{
          width: 22, height: 22, borderRadius: '50%',
          bgcolor: DOT_COLOR[color] ?? '#64748B',
          cursor: onClick ? 'pointer' : 'default',
          mx: 'auto',
          transition: 'transform 0.1s',
          '&:hover': onClick ? { transform: 'scale(1.25)' } : {},
        }}
      />
    </Tooltip>
  );
}

// ── DayCell ───────────────────────────────────────────────────────────────────

function DayCell({ day, dayData, onDotClick, onDrop, draggingRef }) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <Box
      onDragOver={(e) => { if (draggingRef.current) { e.preventDefault(); setDragOver(true); } }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (draggingRef.current) onDrop(day, draggingRef.current);
      }}
      sx={{
        width: 52, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 1,
        bgcolor: dragOver ? 'rgba(245,124,0,0.15)' : 'transparent',
        border: dragOver ? '1px dashed #F57C00' : '1px solid transparent',
        transition: 'background-color 0.1s, border-color 0.1s',
      }}
    >
      {dayData ? (
        <ComplianceDot
          color={dayData.color}
          onClick={() => onDotClick(dayData.assignment_id)}
        />
      ) : (
        <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.04)', mx: 'auto' }} />
      )}
    </Box>
  );
}

// ── SummaryBadge ──────────────────────────────────────────────────────────────

function SummaryBadge({ summary, onClick }) {
  const { compliance_pct, alert } = summary;
  const clickable = !!onClick;

  if (alert === 'inactive_4d') {
    return (
      <Tooltip title="4+ días sin completar — click para enviar mensaje">
        <Typography
          variant="caption"
          onClick={onClick}
          sx={{ color: '#EF4444', fontWeight: 700, cursor: clickable ? 'pointer' : 'default', '&:hover': clickable ? { textDecoration: 'underline' } : {} }}
        >
          ⚠️ Inactivo
        </Typography>
      </Tooltip>
    );
  }
  if (alert === 'overload') {
    return (
      <Tooltip title="Sobrecarga ≥120% — click para enviar mensaje">
        <Typography
          variant="caption"
          onClick={onClick}
          sx={{ color: '#3B82F6', fontWeight: 700, cursor: clickable ? 'pointer' : 'default', '&:hover': clickable ? { textDecoration: 'underline' } : {} }}
        >
          🔵 {compliance_pct}%
        </Typography>
      </Tooltip>
    );
  }
  if (alert === 'praise') {
    return (
      <Tooltip title="¡Semana excelente! — click para felicitar">
        <Typography
          variant="caption"
          onClick={onClick}
          sx={{ color: '#22C55E', fontWeight: 700, cursor: clickable ? 'pointer' : 'default', '&:hover': clickable ? { textDecoration: 'underline' } : {} }}
        >
          🏆 {compliance_pct}%
        </Typography>
      </Tooltip>
    );
  }
  const color = compliance_pct >= 90 ? '#22C55E' : compliance_pct >= 70 ? '#EAB308' : '#EF4444';
  return (
    <Typography variant="caption" sx={{ color, fontWeight: 700 }}>
      {compliance_pct}%
    </Typography>
  );
}

// ── AlertModal ────────────────────────────────────────────────────────────────

// Fallback message templates for historical/offline alerts
const FALLBACK_TEMPLATES = {
  inactive_4d: (name) => `Hola ${name}, hace varios días que no completás entrenamientos. ¿Todo bien? Contame qué pasó.`,
  overload: (name) => `Hola ${name}, esta semana superaste el plan en más de un 20%. Excelente compromiso, pero cuidá el cuerpo. Revisamos juntos la próxima semana.`,
  acwr_spike: (name) => `Hola ${name}, esta semana entrenaste mucho más de lo habitual. Riesgo de sobrecarga elevado. La próxima semana reducimos el volumen.`,
  praise: (name) => `¡${name}! Completaste todos los entrenamientos de la semana. Eso es disciplina de élite. ¡Seguí así! 💪`,
};

function AlertModal({ open, onClose, athleteId, userId, athleteName, orgId, onSent, onError, preAlertType }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [msgText, setMsgText] = useState('');
  const [sending, setSending] = useState(false);

  const firstName = athleteName?.split(' ')[0] ?? athleteName ?? 'atleta';

  useEffect(() => {
    if (!open || !orgId || !athleteId) return;
    setLoading(true);
    setSelectedAlert(null);
    setMsgText('');
    getAthleteAlerts(orgId, athleteId)
      .then((res) => {
        const data = res.data?.alerts ?? [];
        if (data.length > 0) {
          setAlerts(data);
          setSelectedAlert(data[0]);
          setMsgText(data[0].message_template ?? '');
        } else if (preAlertType) {
          // Historical alert: API has no current alert but badge showed one
          // Build a synthetic alert so coach can still send a message
          const syntheticAlert = {
            type: preAlertType,
            severity: preAlertType === 'acwr_spike' ? 'danger' : 'warning',
            message_template: FALLBACK_TEMPLATES[preAlertType]?.(firstName) ?? '',
            phone_number: null,
            days_count: null,
          };
          setAlerts([syntheticAlert]);
          setSelectedAlert(syntheticAlert);
          setMsgText(syntheticAlert.message_template);
        } else {
          setAlerts([]);
        }
      })
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, [open, orgId, athleteId, preAlertType, firstName]);

  const handleSelectAlert = (alert) => {
    setSelectedAlert(alert);
    setMsgText(alert.message_template ?? '');
  };

  const handleSend = async () => {
    if (!msgText.trim() || !selectedAlert) return;
    if (!userId) {
      onError?.('No se pudo identificar al atleta. Recargá la página.');
      return;
    }
    setSending(true);
    try {
      await sendMessage(orgId, {
        recipient_id: userId,   // ← User.pk (not Athlete.pk)
        content: msgText,
        alert_type: selectedAlert.type,
        whatsapp_sent: false,
      });
      onSent?.();
      onClose();
    } catch (err) {
      const detail = err?.response?.data?.detail
        || err?.response?.data?.recipient_id
        || 'Error al enviar el mensaje. Intentá de nuevo.';
      onError?.(Array.isArray(detail) ? detail[0] : detail);
    } finally {
      setSending(false);
    }
  };

  // Show WhatsApp button for any urgent/warning alert when athlete has a phone number
  const URGENT_TYPES = ['acwr_spike', 'inactive_4d', 'overload_sustained'];
  const showWhatsApp =
    URGENT_TYPES.includes(selectedAlert?.type) && selectedAlert?.phone_number;

  const ALERT_LABEL = {
    inactive_4d: '⚠️ Inactividad',
    acwr_spike: '🔴 Sobrecarga ACWR',
    overload: '🔵 Sobrecarga semana',
    overload_sustained: '🔵 Sobrecarga sostenida',
    monotony: '🟡 Monotonía',
    no_plan: '📋 Sin plan',
    streak_positive: '🟢 Racha positiva',
    praise: '🏆 Semana excelente',
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        {selectedAlert ? `${ALERT_LABEL[selectedAlert.type] ?? selectedAlert.type} — ${athleteName}` : `Alertas — ${athleteName}`}
      </DialogTitle>
      <DialogContent dividers>
        {loading && <CircularProgress size={24} sx={{ display: 'block', mx: 'auto', my: 2 }} />}

        {!loading && alerts.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Sin alertas activas para este atleta.
          </Typography>
        )}

        {!loading && alerts.length > 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Alert selector (if multiple) */}
            {alerts.length > 1 && (
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                {alerts.map((a) => (
                  <Button
                    key={a.type}
                    size="small"
                    variant={selectedAlert?.type === a.type ? 'contained' : 'outlined'}
                    onClick={() => handleSelectAlert(a)}
                    sx={{ fontSize: '0.75rem' }}
                  >
                    {ALERT_LABEL[a.type] ?? a.type}
                  </Button>
                ))}
              </Box>
            )}

            {selectedAlert && selectedAlert.type !== 'no_plan' && (
              <>
                {/* Calendar link */}
                <Button
                  size="small"
                  variant="text"
                  sx={{ alignSelf: 'flex-start', color: '#F57C00', pl: 0 }}
                  onClick={() => {
                    // Use the same sessionStorage key Calendar.jsx reads for target selection
                    sessionStorage.setItem('calendarSelectedTarget', `a:${athleteId}`);
                    onClose();
                    // Navigate in same tab — new tab loses auth context
                    window.location.href = '/calendar';
                  }}
                >
                  Ver calendario →
                </Button>

                {/* Message editor */}
                <TextField
                  label="Mensaje para el atleta"
                  multiline
                  minRows={4}
                  value={msgText}
                  onChange={(e) => setMsgText(e.target.value)}
                  fullWidth
                  size="small"
                />
              </>
            )}

            {selectedAlert?.type === 'no_plan' && (
              <Typography variant="body2" color="text.secondary">
                Este atleta no tiene entrenamientos planificados en los próximos 7 días. Revisá su calendario y asigná sesiones.
              </Typography>
            )}
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 2, pb: 2, gap: 1 }}>
        <Button onClick={onClose} color="inherit">Cancelar</Button>
        {showWhatsApp && (
          <Button
            variant="outlined"
            color="success"
            startIcon={<WhatsAppIcon />}
            href={`https://wa.me/${selectedAlert.phone_number}?text=${encodeURIComponent(msgText)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            WhatsApp
          </Button>
        )}
        {selectedAlert && selectedAlert.type !== 'no_plan' && (
          <Button
            variant="contained"
            disabled={sending || !msgText.trim()}
            onClick={handleSend}
            sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#E65100' } }}
          >
            {sending ? 'Enviando…' : 'Enviar →'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Plantilla() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id ?? null;
  const navigate = useNavigate();

  // Week navigation
  const [weekMonday, setWeekMonday] = useState(() => getMondayOf(new Date()));
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekMonday, i));

  // Teams
  const [teamsState, teamsDispatch] = useReducer(fetchReducer, { data: [], loading: false, error: null });
  const teams = teamsState.data;
  const [selectedTeamId, setSelectedTeamId] = useState('');

  // Compliance data
  const [complianceState, complianceDispatch] = useReducer(fetchReducer, {
    data: null, loading: false, error: null,
  });

  // Checkboxes
  const [selected, setSelected] = useState(new Set());

  // Drawer
  const [drawerEvent, setDrawerEvent] = useState(null);

  // Library sidebar
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const draggingWorkoutRef = useRef(null);

  // Snackbar
  const [snack, setSnack] = useState({ open: false, message: '', severity: 'success' });

  // Alert modal
  const [alertModal, setAlertModal] = useState({ open: false, athleteId: null, userId: null, athleteName: '', preAlertType: null });

  // ── Load teams ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!orgId) return;
    teamsDispatch({ type: 'FETCH_START' });
    getTeams(orgId)
      .then((res) => {
        const data = res.data?.results ?? res.data ?? [];
        teamsDispatch({ type: 'FETCH_SUCCESS', data });
        if (data.length > 0) setSelectedTeamId(data[0].id);
      })
      .catch(() => teamsDispatch({ type: 'FETCH_ERROR', error: 'Error cargando equipos.' }));
  }, [orgId]);

  // ── Load compliance week ────────────────────────────────────────────────────

  useEffect(() => {
    if (!orgId || !selectedTeamId) return;
    complianceDispatch({ type: 'FETCH_START' });
    getComplianceWeek(orgId, selectedTeamId, toISO(weekMonday))
      .then((res) => {
        complianceDispatch({ type: 'FETCH_SUCCESS', data: res.data });
        setSelected(new Set()); // reset checkboxes after successful load
      })
      .catch(() => complianceDispatch({ type: 'FETCH_ERROR', error: 'No se pudo cargar la plantilla.' }));
  }, [orgId, selectedTeamId, weekMonday]);

  // ── Week navigation ─────────────────────────────────────────────────────────

  const prevWeek = () => setWeekMonday((w) => addDays(w, -7));
  const nextWeek = () => setWeekMonday((w) => addDays(w, 7));
  const goToday  = () => setWeekMonday(getMondayOf(new Date()));

  // ── Checkbox logic ──────────────────────────────────────────────────────────

  const athletes = complianceState.data?.athletes ?? [];

  const toggleAll = () => {
    if (selected.size === athletes.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(athletes.map((a) => a.athlete_id)));
    }
  };

  const toggleAthlete = (athleteId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(athleteId)) next.delete(athleteId);
      else next.add(athleteId);
      return next;
    });
  };

  // ── Click on dot → open drawer ─────────────────────────────────────────────

  const handleDotClick = async (assignmentId) => {
    if (!assignmentId) return;
    try {
      const res = await getAssignment(orgId, assignmentId);
      const a = res.data;
      setDrawerEvent({
        id: a.id,
        title: a.planned_workout?.name ?? '',
        resource: a,
      });
    } catch {
      // Silently ignore
    }
  };

  // ── Click on athlete name → navigate to calendar ────────────────────────────

  const handleAthleteClick = (athleteId, athleteName) => {
    sessionStorage.setItem('plantilla_selected_athlete_id', athleteId);
    sessionStorage.setItem('plantilla_selected_athlete_name', athleteName);
    navigate('/calendar');
  };

  // ── Drag & drop from library ────────────────────────────────────────────────

  const handleDragStart = useCallback((workout) => {
    draggingWorkoutRef.current = workout;
  }, []);

  const handleDragEnd = useCallback(() => {
    draggingWorkoutRef.current = null;
  }, []);

  const handleDrop = async (day, workout) => {
    if (selected.size === 0) {
      setSnack({ open: true, message: 'Seleccioná al menos un atleta', severity: 'warning' });
      return;
    }
    const athleteIds = Array.from(selected);
    try {
      const res = await bulkCreateAssignments(orgId, {
        athlete_ids: athleteIds,
        planned_workout_id: workout.id,
        scheduled_date: toISO(day),
      });
      const { created, skipped } = res.data;
      setSnack({
        open: true,
        message: `${created} sesión${created !== 1 ? 'es' : ''} creada${created !== 1 ? 's' : ''} · ${skipped} omitida${skipped !== 1 ? 's' : ''}`,
        severity: 'success',
      });
      if (orgId && selectedTeamId) {
        complianceDispatch({ type: 'FETCH_START' });
        getComplianceWeek(orgId, selectedTeamId, toISO(weekMonday))
          .then((r) => complianceDispatch({ type: 'FETCH_SUCCESS', data: r.data }))
          .catch(() => complianceDispatch({ type: 'FETCH_ERROR', error: 'Error recargando.' }));
      }
    } catch {
      setSnack({ open: true, message: 'Error al asignar. Intentá de nuevo.', severity: 'error' });
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const allSelected = athletes.length > 0 && selected.size === athletes.length;
  const someSelected = selected.size > 0 && !allSelected;

  return (
    <Layout>
      <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden', bgcolor: '#0f1623' }}>

        {/* ── Main content ── */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Header */}
          <Box sx={{
            px: 3, py: 2,
            borderBottom: '1px solid rgba(255,255,255,0.07)',
            display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap',
          }}>
            <Typography variant="h6" sx={{ color: '#f1f5f9', fontWeight: 700, letterSpacing: 0.5 }}>
              Plantilla de Entrenamiento
            </Typography>

            {/* Team selector */}
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel sx={{ color: '#64748b' }}>Equipo</InputLabel>
              <Select
                value={selectedTeamId}
                label="Equipo"
                onChange={(e) => setSelectedTeamId(e.target.value)}
                disabled={teamsState.loading}
                sx={{
                  color: '#e2e8f0',
                  '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.12)' },
                  '.MuiSvgIcon-root': { color: '#64748b' },
                }}
              >
                {teams.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
                ))}
                {teams.length === 0 && <MenuItem disabled>Sin equipos</MenuItem>}
              </Select>
            </FormControl>

            {/* Week navigation */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 'auto' }}>
              <IconButton size="small" onClick={prevWeek} sx={{ color: '#94a3b8' }}>
                <ChevronLeft />
              </IconButton>
              <Typography variant="body2" sx={{ color: '#e2e8f0', minWidth: 160, textAlign: 'center' }}>
                {formatWeekLabel(weekMonday)}
              </Typography>
              <IconButton size="small" onClick={goToday} sx={{ color: '#94a3b8' }} title="Hoy">
                <Today fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={nextWeek} sx={{ color: '#94a3b8' }}>
                <ChevronRight />
              </IconButton>
            </Box>
          </Box>

          {/* Table area */}
          <Box sx={{ flex: 1, overflowY: 'auto', px: 2, py: 1.5 }}>
            {complianceState.loading && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
                <CircularProgress sx={{ color: '#F57C00' }} />
              </Box>
            )}
            {complianceState.error && (
              <Alert severity="error" sx={{ mt: 2 }}>{complianceState.error}</Alert>
            )}
            {!complianceState.loading && !complianceState.error && complianceState.data && (
              <Box sx={{ overflowX: 'auto' }}>
                {/* Table */}
                <Box component="table" sx={{ borderCollapse: 'collapse', width: '100%', minWidth: 700 }}>
                  <Box component="thead">
                    <Box component="tr">
                      {/* Checkbox header */}
                      <Box component="th" sx={{ width: 40, p: 0.5, textAlign: 'center' }}>
                        <Checkbox
                          size="small"
                          checked={allSelected}
                          indeterminate={someSelected}
                          onChange={toggleAll}
                          sx={{ color: '#64748b', '&.Mui-checked': { color: '#F57C00' }, '&.MuiCheckbox-indeterminate': { color: '#F57C00' } }}
                        />
                      </Box>
                      {/* Athlete col */}
                      <Box component="th" sx={{ p: 1, textAlign: 'left' }}>
                        <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
                          Atleta
                        </Typography>
                      </Box>
                      {/* Day cols */}
                      {weekDays.map((day, idx) => (
                        <Box component="th" key={idx} sx={{ width: 52, p: 0.5, textAlign: 'center' }}>
                          <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, display: 'block' }}>
                            {DAY_LABELS[idx]}
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#475569', fontSize: '0.65rem' }}>
                            {day.getDate()}
                          </Typography>
                        </Box>
                      ))}
                      {/* Summary col */}
                      <Box component="th" sx={{ width: 80, p: 0.5, textAlign: 'center' }}>
                        <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
                          Semana
                        </Typography>
                      </Box>
                    </Box>
                  </Box>

                  <Box component="tbody">
                    {athletes.map((athlete) => (
                      <Box
                        component="tr"
                        key={athlete.athlete_id}
                        sx={{
                          borderTop: '1px solid rgba(255,255,255,0.05)',
                          bgcolor: selected.has(athlete.athlete_id) ? 'rgba(245,124,0,0.06)' : 'transparent',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' },
                        }}
                      >
                        {/* Checkbox */}
                        <Box component="td" sx={{ textAlign: 'center', p: 0.5 }}>
                          <Checkbox
                            size="small"
                            checked={selected.has(athlete.athlete_id)}
                            onChange={() => toggleAthlete(athlete.athlete_id)}
                            sx={{ color: '#64748b', '&.Mui-checked': { color: '#F57C00' } }}
                          />
                        </Box>
                        {/* Athlete name */}
                        <Box component="td" sx={{ p: 1, minWidth: 140 }}>
                          <Typography
                            variant="body2"
                            onClick={() => handleAthleteClick(athlete.athlete_id, athlete.athlete_name)}
                            sx={{
                              color: '#cbd5e1', cursor: 'pointer', fontWeight: 500,
                              '&:hover': { color: '#F57C00', textDecoration: 'underline' },
                            }}
                            noWrap
                          >
                            {athlete.athlete_name}
                          </Typography>
                        </Box>
                        {/* Day cells */}
                        {weekDays.map((day, idx) => {
                          const iso = toISO(day);
                          const dayData = athlete.days?.[iso] ?? null;
                          return (
                            <Box component="td" key={idx} sx={{ p: 0.25, textAlign: 'center' }}>
                              <DayCell
                                day={day}
                                dayData={dayData}
                                onDotClick={handleDotClick}
                                onDrop={handleDrop}
                                draggingRef={draggingWorkoutRef}
                              />
                            </Box>
                          );
                        })}
                        {/* Summary */}
                        <Box component="td" sx={{ textAlign: 'center', p: 0.5 }}>
                          <SummaryBadge
                            summary={athlete.summary}
                            onClick={athlete.summary.alert ? () => setAlertModal({
                              open: true,
                              athleteId: athlete.athlete_id,
                              userId: athlete.user_id,
                              athleteName: athlete.athlete_name,
                              preAlertType: athlete.summary.alert,
                            }) : undefined}
                          />
                        </Box>
                      </Box>
                    ))}

                    {athletes.length === 0 && (
                      <Box component="tr">
                        <Box component="td" colSpan={10} sx={{ textAlign: 'center', py: 6 }}>
                          <Typography variant="body2" sx={{ color: '#475569' }}>
                            Sin atletas en este equipo
                          </Typography>
                        </Box>
                      </Box>
                    )}
                  </Box>
                </Box>
              </Box>
            )}

            {!complianceState.loading && !complianceState.data && !selectedTeamId && (
              <Box sx={{ textAlign: 'center', mt: 8 }}>
                <Typography variant="body2" sx={{ color: '#475569' }}>
                  Seleccioná un equipo para ver la plantilla
                </Typography>
              </Box>
            )}
          </Box>

          {/* ── Bottom action bar (when ≥1 selected) ── */}
          {selected.size > 0 && (
            <Box sx={{
              px: 3, py: 1.5,
              borderTop: '1px solid rgba(255,255,255,0.07)',
              bgcolor: '#131e2e',
              display: 'flex', alignItems: 'center', gap: 2,
            }}>
              <Typography variant="body2" sx={{ color: '#94a3b8' }}>
                {selected.size} seleccionado{selected.size !== 1 ? 's' : ''}
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748b' }}>
                · Arrastrá un entrenamiento sobre un día para asignarlo
              </Typography>
            </Box>
          )}
        </Box>

        {/* ── Library sidebar ── */}
        <LibrarySidebar
          orgId={orgId}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
        />
      </Box>

      {/* ── WorkoutCoachDrawer ── */}
      <WorkoutCoachDrawer
        event={drawerEvent}
        orgId={orgId}
        onClose={() => setDrawerEvent(null)}
        onSaved={() => {
          setDrawerEvent(null);
          // Refresh compliance after save
          if (orgId && selectedTeamId) {
            complianceDispatch({ type: 'FETCH_START' });
            getComplianceWeek(orgId, selectedTeamId, toISO(weekMonday))
              .then((r) => complianceDispatch({ type: 'FETCH_SUCCESS', data: r.data }))
              .catch(() => {});
          }
        }}
      />

      <AlertModal
        open={alertModal.open}
        onClose={() => setAlertModal((s) => ({ ...s, open: false }))}
        athleteId={alertModal.athleteId}
        userId={alertModal.userId}
        athleteName={alertModal.athleteName}
        orgId={orgId}
        preAlertType={alertModal.preAlertType}
        onSent={() => setSnack({ open: true, message: 'Mensaje enviado ✓', severity: 'success' })}
        onError={(msg) => setSnack({ open: true, message: msg, severity: 'error' })}
      />

      {/* ── Snackbar ── */}
      <Snackbar
        open={snack.open}
        autoHideDuration={4000}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        message={snack.message}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        ContentProps={{
          sx: {
            bgcolor: snack.severity === 'success' ? '#16a34a'
              : snack.severity === 'warning' ? '#d97706' : '#dc2626',
          }
        }}
      />
    </Layout>
  );
}
