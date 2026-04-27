/**
 * calendarHelpers.js — Shared calendar utilities (PR-163)
 * Used by CalendarGrid, AthleteMyTraining, Calendar
 */
import {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek, eachDayOfInterval,
} from 'date-fns';

// ── Sport metadata ────────────────────────────────────────────────────────────

export const SPORT_COLOR = {
  trail:    '#f97316',
  run:      '#22c55e',
  bike:     '#3b82f6',
  cycling:  '#3b82f6',
  strength: '#a855f7',
  mobility: '#06b6d4',
  swim:     '#0ea5e9',
  other:    '#94a3b8',
};

export const SPORT_LABEL = {
  trail:    'Trail',
  run:      'Running',
  bike:     'Ciclismo',
  cycling:  'Ciclismo',
  strength: 'Fuerza',
  mobility: 'Movilidad',
  swim:     'Natación',
  other:    'Otro',
};

export function sportColor(discipline) {
  return SPORT_COLOR[discipline] ?? '#94a3b8';
}

export function sportLabel(discipline) {
  return SPORT_LABEL[discipline] ?? discipline ?? 'Otro';
}

// ── Formatting ────────────────────────────────────────────────────────────────

export function fmtDuration(seconds) {
  if (!seconds) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h${m > 0 ? ` ${m}min` : ''}`;
  return `${m}min`;
}

export function fmtDistance(meters) {
  if (!meters) return null;
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}km`;
  return `${meters}m`;
}

// ── Month grid builder ────────────────────────────────────────────────────────

export function buildCalendarWeeks(currentDate) {
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 1 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start: calStart, end: calEnd });
  const weeks = [];
  for (let i = 0; i < days.length; i += 7) {
    weeks.push(days.slice(i, i + 7));
  }
  return weeks;
}

// ── Compliance — 6-range (no 150% cap) ───────────────────────────────────────

/**
 * Compute compliance percentage for a WorkoutAssignment.
 * Prefers backend-computed value (ADR-004); falls back to local calculation.
 */
export function computeCompliancePct(assignment) {
  if (assignment.compliance_pct != null) return assignment.compliance_pct;
  const pw = assignment.planned_workout;
  const plannedM = pw?.estimated_distance_meters;
  const actualM = assignment.actual_distance_meters;
  const plannedS = pw?.estimated_duration_seconds;
  const actualS = assignment.actual_duration_seconds;
  if (plannedM && actualM != null) return Math.round((actualM / plannedM) * 100);
  if (plannedS && actualS != null) return Math.round((actualS / plannedS) * 100);
  return null;
}

/**
 * Returns visual style tokens for a compliance percentage.
 * isPast: whether the scheduled date is in the past
 * isCompleted: whether the assignment has status='completed'
 */
export function getComplianceStyle(pct, isPast, isCompleted) {
  if (!isCompleted) {
    if (isPast) {
      // Past unfinished — very subtle red tint, compliance badge is the primary indicator
      return { borderColor: '#e2e8f0', bgColor: '#fef2f2', label: 'Sin completar', dotColor: '#ef4444' };
    }
    return { borderColor: '#e2e8f0', bgColor: '#ffffff', label: 'Planificado', dotColor: '#94a3b8' };
  }
  // Completed — subtle tint backgrounds; compliance % badge is the primary visual indicator
  if (pct == null)   return { borderColor: '#e2e8f0', bgColor: '#f0fdf4', label: 'Completado',    dotColor: '#16a34a' };
  if (pct === 0)     return { borderColor: '#e2e8f0', bgColor: '#fef2f2', label: 'Sin completar', dotColor: '#ef4444' };
  if (pct <= 30)     return { borderColor: '#e2e8f0', bgColor: '#fef2f2', label: 'Muy parcial',   dotColor: '#ef4444' };
  if (pct <= 70)     return { borderColor: '#e2e8f0', bgColor: '#fffbeb', label: 'Parcial',       dotColor: '#d97706' };
  if (pct <= 110)    return { borderColor: '#e2e8f0', bgColor: '#f0fdf4', label: 'Completado',    dotColor: '#16a34a' };
  if (pct <= 150)    return { borderColor: '#e2e8f0', bgColor: '#eff6ff', label: 'Sobre-cumplido',dotColor: '#3b82f6' };
  return             { borderColor: '#e2e8f0', bgColor: '#faf5ff', label: '⚠️ Exceso',            dotColor: '#7c3aed' };
}

// ── Constants ────────────────────────────────────────────────────────────────

export const DAY_HEADERS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];

export const TRAINING_PHASE_CONFIG = {
  carga:    { emoji: '🟢', label: 'CARGA',    color: '#f97316' },
  descarga: { emoji: '🟡', label: 'DESCARGA', color: '#22c55e' },
  carrera:  { emoji: '🔴', label: 'CARRERA',  color: '#ef4444' },
  descanso: { emoji: '🔵', label: 'DESCANSO', color: '#3b82f6' },
  lesion:   { emoji: '🔴', label: 'LESIÓN',   color: '#6b7280' },
};

// ── Menstrual cycle helpers ───────────────────────────────────────────────────

export const MENSTRUAL_PHASES = [
  { name: 'Menstrual', color: '#EF4444', tip: 'Fase menstrual — escuchá a tu cuerpo' },
  { name: 'Folicular', color: '#00D4AA', tip: 'Fase folicular — ideal para alta intensidad' },
  { name: 'Ovulación', color: '#F59E0B', tip: 'Ovulación — pico de energía' },
  { name: 'Lútea',     color: '#F97316', tip: 'Fase lútea — considerá reducir intensidad' },
];

export function getMenstrualPhaseForDate(dateObj, lastPeriodDate, cycleDays) {
  if (!lastPeriodDate || !cycleDays) return null;
  const last = new Date(lastPeriodDate);
  const daysSince = Math.floor((dateObj - last) / 86400000);
  const dayInCycle = ((daysSince % cycleDays) + cycleDays) % cycleDays;
  if (dayInCycle <= 4)  return MENSTRUAL_PHASES[0];
  if (dayInCycle <= 12) return MENSTRUAL_PHASES[1];
  if (dayInCycle <= 14) return MENSTRUAL_PHASES[2];
  return MENSTRUAL_PHASES[3];
}

// day_of_week: 0=Mon…6=Sun  ↔  JS getDay(): 0=Sun,1=Mon…6=Sat
export function jsWeekdayToAvailIndex(jsDay) {
  return (jsDay + 6) % 7;
}
