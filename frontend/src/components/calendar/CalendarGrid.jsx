/**
 * CalendarGrid.jsx — Shared custom month grid for coach + athlete (PR-163)
 *
 * Replaces react-big-calendar's month view with rich WorkoutCards.
 * Supports both coach (drag/context-menu) and athlete (mark-complete) roles.
 *
 * Props:
 *   assignments      — raw assignment objects array
 *   goalDateMap      — { 'YYYY-MM-DD': goalObj }
 *   planVsRealMap    — { 'YYYY-MM-DD': pvr }  keyed by week Monday
 *   pmcData          — { ctl, atl, tsb } | null
 *   trainingPhaseMap — { 'YYYY-MM-DD': 'carga'|... } keyed by Monday
 *   role             — 'coach' | 'athlete'
 *   currentDate      — Date (controlled)
 *   onNavigate       — (date) => void
 *   loading          — boolean
 *   onCardClick      — (assignment) => void
 *   onCompleteClick  — (assignment) => void
 *   onContextMenu    — (x, y, assignment) => void
 *   onMoveAssignment — (assignmentId, newDateStr) => void
 *   onDropFromLibrary— (dateStr) => void  (library card was dropped on this date)
 *   draggingWorkoutRef — React.ref  (tracks active sidebar drag)
 *   availability     — AthleteAvailability[]
 *   athleteProfile   — { menstrual_tracking_enabled, last_period_date, menstrual_cycle_days } | null
 *   onGoalClick      — (goal) => void
 */
import React, { useRef, useState } from 'react';
import { Box, Typography, IconButton, Paper, useTheme, useMediaQuery } from '@mui/material';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';
import { format, isSameDay, isSameMonth } from 'date-fns';
import { es } from 'date-fns/locale';
import {
  buildCalendarWeeks, DAY_HEADERS, jsWeekdayToAvailIndex,
  getMenstrualPhaseForDate, TRAINING_PHASE_CONFIG,
} from '../../utils/calendarHelpers';
import { addMonths, subMonths } from 'date-fns';
import WorkoutCard from './WorkoutCard';
import GoalCard from './GoalCard';
import WeekHeader from './WeekHeader';

export default function CalendarGrid({
  assignments = [],
  goalDateMap = {},
  planVsRealMap = {},
  pmcData = null,
  trainingPhaseMap = {},
  role = 'athlete',
  currentDate,
  onNavigate,
  loading = false,
  onCardClick,
  onCompleteClick,
  onContextMenu,
  onMoveAssignment,
  onDropFromLibrary,
  draggingWorkoutRef,
  availability = [],
  athleteProfile = null,
  onGoalClick,
}) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const today = new Date();
  // Up to 6 weeks — months starting on Fri/Sat can span 5–6 partial weeks
  const weeks = buildCalendarWeeks(currentDate);

  // Track which card is being dragged internally (coach move)
  const draggingCardIdRef = useRef(null);
  const [dropTargetDate, setDropTargetDate] = useState(null);

  // Mobile touch/pull-to-refresh state (used only when isMobile)
  const mobileTouchStartXRef = useRef(null);
  const mobileTouchStartYRef = useRef(null);
  const [mobilePulling, setMobilePulling] = useState(false);

  // Build assignment index: { 'YYYY-MM-DD': [assignment, ...] }
  const assignmentsByDate = {};
  for (const a of assignments) {
    const key = a.scheduled_date;
    if (!assignmentsByDate[key]) assignmentsByDate[key] = [];
    assignmentsByDate[key].push(a);
  }

  // Build blocked day map: availIndex → availability record
  const blockedDayMap = {};
  for (const av of availability) {
    if (!av.is_available) blockedDayMap[av.day_of_week] = av;
  }

  // ── Drag handlers (coach only) ────────────────────────────────────────────

  const handleCardDragStart = (e, assignment) => {
    draggingCardIdRef.current = assignment.id;
  };

  const handleCardDragEnd = () => {
    draggingCardIdRef.current = null;
    setDropTargetDate(null);
  };

  const handleDayDragOver = (e, dateKey) => {
    // Allow drop only if something is being dragged
    const hasCard = draggingCardIdRef.current != null;
    const hasLibrary = draggingWorkoutRef?.current != null;
    if (!hasCard && !hasLibrary) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = hasCard ? 'move' : 'copy';
    setDropTargetDate(dateKey);
  };

  const handleDayDragLeave = () => {
    setDropTargetDate(null);
  };

  const handleDayDrop = (e, dateKey) => {
    e.preventDefault();
    setDropTargetDate(null);

    if (draggingCardIdRef.current != null) {
      // Moving an existing card to a new date
      const assignmentId = draggingCardIdRef.current;
      draggingCardIdRef.current = null;
      onMoveAssignment?.(assignmentId, dateKey);
    } else if (draggingWorkoutRef?.current != null) {
      // Dropping a library workout onto this date
      onDropFromLibrary?.(dateKey);
    }
  };

  // ── Mobile list view (xs only) ───────────────────────────────────────────
  if (isMobile) {
    const DAY_ABBR = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

    const handleMobileTouchStart = (e) => {
      mobileTouchStartXRef.current = e.touches[0].clientX;
      mobileTouchStartYRef.current = e.touches[0].clientY;
    };

    const handleMobileTouchEnd = (e) => {
      const startY = mobileTouchStartYRef.current;
      const startX = mobileTouchStartXRef.current;
      if (startY === null || startX === null) return;

      const dy = e.changedTouches[0].clientY - startY;
      const dx = e.changedTouches[0].clientX - startX;

      // Horizontal swipe → change month
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
        if (dx < 0) onNavigate(addMonths(currentDate, 1));
        else onNavigate(subMonths(currentDate, 1));
      }

      // Vertical pull-down > 60px → refresh
      if (dy > 60 && Math.abs(dy) > Math.abs(dx)) {
        setMobilePulling(true);
        setTimeout(() => setMobilePulling(false), 1000);
        onNavigate(new Date(currentDate));
      }

      mobileTouchStartXRef.current = null;
      mobileTouchStartYRef.current = null;
    };

    return (
      <Paper
        sx={{ borderRadius: 3, overflow: 'hidden', border: '1px solid #e2e8f0', boxShadow: 'none' }}
        onTouchStart={handleMobileTouchStart}
        onTouchEnd={handleMobileTouchEnd}
      >
        {/* Month navigation header */}
        <Box sx={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          px: 2, py: 1, borderBottom: '1px solid #e2e8f0', bgcolor: '#f8fafc',
        }}>
          <IconButton size="small" onClick={() => onNavigate(subMonths(currentDate, 1))}
            sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
            <ChevronLeft fontSize="small" />
          </IconButton>
          {mobilePulling && (
            <Typography variant="caption" sx={{ color: '#00D4AA', fontSize: '0.7rem', fontWeight: 600 }}>
              Actualizando...
            </Typography>
          )}
          <Typography variant="subtitle1" sx={{
            fontWeight: 700, color: '#1e293b', textTransform: 'capitalize', letterSpacing: 0.3,
          }}>
            {format(currentDate, 'MMMM yyyy', { locale: es })}
          </Typography>
          <IconButton size="small" onClick={() => onNavigate(addMonths(currentDate, 1))}
            sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Box>

        {/* Week sections — vertical list */}
        <Box sx={{ bgcolor: 'white' }}>
          {weeks.map((week, wIdx) => {
            const weekDateKeys = week.map((d) => format(d, 'yyyy-MM-dd'));
            const weekAssignments = weekDateKeys.flatMap((k) => assignmentsByDate[k] ?? []);
            const weekMondayKey = format(week[0], 'yyyy-MM-dd');
            const pvr = planVsRealMap[weekMondayKey] ?? null;
            const trainingPhase = trainingPhaseMap[weekMondayKey] ?? null;

            // Find which days in this week have sessions or goals
            const activeDays = week.filter((d) => {
              const dk = format(d, 'yyyy-MM-dd');
              return (assignmentsByDate[dk]?.length > 0) || goalDateMap[dk];
            });

            // Collect empty in-month days grouped into one line
            const emptyInMonthDays = week.filter((d) => {
              const dk = format(d, 'yyyy-MM-dd');
              return isSameMonth(d, currentDate) && !assignmentsByDate[dk]?.length && !goalDateMap[dk];
            });

            return (
              <React.Fragment key={wIdx}>
                {/* Week separator */}
                {wIdx > 0 && <Box sx={{ height: 1, bgcolor: '#e2e8f0' }} />}

                {/* Training phase strip */}
                {trainingPhase && (() => {
                  const phaseMeta = TRAINING_PHASE_CONFIG[trainingPhase];
                  return phaseMeta ? <Box sx={{ height: 3, bgcolor: phaseMeta.color, opacity: 0.6 }} /> : null;
                })()}

                {/* Week header (plan vs real) */}
                {weekAssignments.length > 0 && (
                  <Box sx={{ px: 2, pt: 1.5 }}>
                    <WeekHeader
                      planVsReal={pvr}
                      weekAssignments={weekAssignments}
                      pmcData={pmcData}
                      trainingPhase={trainingPhase}
                    />
                  </Box>
                )}

                {/* Empty days — single gray "rest" line */}
                {emptyInMonthDays.length > 0 && activeDays.length > 0 && (
                  <Box sx={{ px: 2, py: 0.75 }}>
                    <Typography variant="caption" sx={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.72rem' }}>
                      {emptyInMonthDays.map((d) => `${DAY_ABBR[d.getDay()]} ${format(d, 'd')}`).join(' — ')}: Descanso
                    </Typography>
                  </Box>
                )}

                {/* If the entire week is empty (rest week) */}
                {activeDays.length === 0 && week.some((d) => isSameMonth(d, currentDate)) && (
                  <Box sx={{ px: 2, py: 1.25 }}>
                    <Typography variant="caption" sx={{ color: '#cbd5e1', fontStyle: 'italic', fontSize: '0.72rem' }}>
                      {week.filter((d) => isSameMonth(d, currentDate))
                        .map((d) => `${DAY_ABBR[d.getDay()]} ${format(d, 'd')}`).join(' — ')}: Descanso
                    </Typography>
                  </Box>
                )}

                {/* Active days — full-width cards */}
                {activeDays.map((day) => {
                  const dateKey = format(day, 'yyyy-MM-dd');
                  const dayAssignments = assignmentsByDate[dateKey] ?? [];
                  const isToday = isSameDay(day, today);
                  const isPast = day < today && !isToday;

                  return (
                    <Box key={dateKey} sx={{ px: 2, pb: 1, pt: 0.5 }}>
                      {/* Day label */}
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Box sx={{
                          width: 22, height: 22,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          borderRadius: '50%',
                          bgcolor: isToday ? '#f97316' : 'transparent',
                          flexShrink: 0,
                        }}>
                          <Typography variant="caption" sx={{
                            fontWeight: isToday ? 700 : 600,
                            color: isToday ? 'white' : '#374151',
                            fontSize: '0.72rem',
                          }}>
                            {format(day, 'd')}
                          </Typography>
                        </Box>
                        <Typography variant="caption" sx={{
                          fontWeight: 600, color: isToday ? '#f97316' : '#64748b',
                          fontSize: '0.72rem', textTransform: 'capitalize',
                        }}>
                          {DAY_ABBR[day.getDay()]}
                        </Typography>
                      </Box>

                      {/* Goal card */}
                      {goalDateMap[dateKey] && (
                        <GoalCard goal={goalDateMap[dateKey]} onClick={onGoalClick} />
                      )}

                      {/* Assignment cards — full width */}
                      {dayAssignments.map((a) => (
                        <WorkoutCard
                          key={a.id}
                          assignment={a}
                          role={role}
                          isPast={isPast}
                          onClick={onCardClick}
                          onCompleteClick={onCompleteClick}
                          onContextMenu={onContextMenu}
                          onDragStart={() => {}}
                          onDragEnd={() => {}}
                        />
                      ))}
                    </Box>
                  );
                })}
              </React.Fragment>
            );
          })}
        </Box>
      </Paper>
    );
  }

  return (
    <Paper sx={{ borderRadius: 3, overflow: 'hidden', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
      {/* Month navigation header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 1,
          borderBottom: '1px solid #e2e8f0',
          bgcolor: '#f8fafc',
        }}
      >
        <IconButton
          size="small"
          onClick={() => onNavigate(subMonths(currentDate, 1))}
          sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}
        >
          <ChevronLeft fontSize="small" />
        </IconButton>
        <Typography
          variant="subtitle1"
          sx={{ fontWeight: 700, color: '#1e293b', textTransform: 'capitalize', letterSpacing: 0.3 }}
        >
          {format(currentDate, 'MMMM yyyy', { locale: es })}
        </Typography>
        <IconButton
          size="small"
          onClick={() => onNavigate(addMonths(currentDate, 1))}
          sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}
        >
          <ChevronRight fontSize="small" />
        </IconButton>
      </Box>

      {/* Day-of-week headers */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, 1fr)',
          bgcolor: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        {DAY_HEADERS.map((d) => (
          <Box key={d} sx={{ py: 0.75, textAlign: 'center' }}>
            <Typography
              variant="caption"
              sx={{ fontWeight: 700, color: '#94a3b8', fontSize: '0.65rem', letterSpacing: 0.5 }}
            >
              {d}
            </Typography>
          </Box>
        ))}
      </Box>

      {/* Week rows */}
      {weeks.map((week, wIdx) => {
        const weekDateKeys = week.map((d) => format(d, 'yyyy-MM-dd'));
        const weekAssignments = weekDateKeys.flatMap((k) => assignmentsByDate[k] ?? []);
        const weekMondayKey = format(week[0], 'yyyy-MM-dd');
        const pvr = planVsRealMap[weekMondayKey] ?? null;
        const trainingPhase = trainingPhaseMap[weekMondayKey] ?? null;
        const phaseMeta = trainingPhase ? TRAINING_PHASE_CONFIG[trainingPhase] : null;

        return (
          <React.Fragment key={wIdx}>
            {/* Week phase strip */}
            {phaseMeta && (
              <Box sx={{ height: 3, bgcolor: phaseMeta.color, opacity: 0.6 }} />
            )}

            {/* Day cells */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
              }}
            >
              {week.map((day, dIdx) => {
                const dateKey = format(day, 'yyyy-MM-dd');
                const dayAssignments = assignmentsByDate[dateKey] ?? [];
                const isToday = isSameDay(day, today);
                const inMonth = isSameMonth(day, currentDate);
                const isPast = day < today && !isToday;
                const availIdx = jsWeekdayToAvailIndex(day.getDay());
                const blocked = inMonth ? blockedDayMap[availIdx] : null;
                const menstrualPhase = inMonth && athleteProfile?.menstrual_tracking_enabled
                  ? getMenstrualPhaseForDate(
                      day,
                      athleteProfile.last_period_date,
                      athleteProfile.menstrual_cycle_days,
                    )
                  : null;
                const isDropTarget = dropTargetDate === dateKey;
                const hasUnfinishedPast = isPast && dayAssignments.some((a) => a.status !== 'completed');

                return (
                  <Box
                    key={dIdx}
                    onDragOver={role === 'coach' ? (e) => handleDayDragOver(e, dateKey) : undefined}
                    onDragLeave={role === 'coach' ? handleDayDragLeave : undefined}
                    onDrop={role === 'coach' ? (e) => handleDayDrop(e, dateKey) : undefined}
                    sx={{
                      minHeight: 88,
                      p: 0.75,
                      borderRight: dIdx < 6 ? '1px solid #e2e8f0' : 'none',
                      borderBottom: wIdx < weeks.length - 1 ? 'none' : 'none',
                      bgcolor: isDropTarget
                        ? 'rgba(249,115,22,0.08)'
                        : blocked
                        ? '#f1f5f9'
                        : isToday
                        ? '#FFF7ED'
                        : hasUnfinishedPast
                        ? 'rgba(239,68,68,0.04)'
                        : inMonth
                        ? 'white'
                        : '#f8fafc',
                      position: 'relative',
                      transition: 'background-color 0.1s',
                      outline: isDropTarget ? '2px dashed #f97316' : 'none',
                      outlineOffset: -2,
                    }}
                  >
                    {/* Menstrual phase stripe */}
                    {menstrualPhase && (
                      <Box
                        title={menstrualPhase.tip}
                        sx={{
                          position: 'absolute', top: 0, left: 0, right: 0,
                          height: 3, bgcolor: menstrualPhase.color,
                          borderRadius: '2px 2px 0 0', zIndex: 1,
                        }}
                      />
                    )}

                    {/* Day number */}
                    <Box
                      sx={{
                        width: 22, height: 22,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        borderRadius: '50%',
                        bgcolor: isToday ? '#f97316' : 'transparent',
                        mb: 0.5,
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{
                          fontWeight: isToday ? 700 : 400,
                          color: isToday ? 'white' : inMonth ? '#374151' : '#cbd5e1',
                          fontSize: '0.7rem',
                        }}
                      >
                        {format(day, 'd')}
                      </Typography>
                    </Box>

                    {/* Blocked day indicator */}
                    {blocked && (
                      <Typography
                        variant="caption"
                        sx={{ display: 'block', fontSize: '0.58rem', color: '#94a3b8', fontStyle: 'italic', mb: 0.25, lineHeight: 1.2 }}
                      >
                        {blocked.reason || 'No disponible'}
                      </Typography>
                    )}

                    {/* Goal card */}
                    {inMonth && goalDateMap[dateKey] && (
                      <GoalCard goal={goalDateMap[dateKey]} onClick={onGoalClick} />
                    )}

                    {/* Assignment cards — all stacked, no truncation */}
                    {dayAssignments.map((a) => (
                      <WorkoutCard
                        key={a.id}
                        assignment={a}
                        role={role}
                        isPast={isPast}
                        onClick={onCardClick}
                        onCompleteClick={onCompleteClick}
                        onContextMenu={onContextMenu}
                        onDragStart={handleCardDragStart}
                        onDragEnd={handleCardDragEnd}
                      />
                    ))}
                  </Box>
                );
              })}
            </Box>

            {/* Week summary: plan vs real + metrics + phase badge */}
            <WeekHeader
              planVsReal={pvr}
              weekAssignments={weekAssignments}
              pmcData={pmcData}
              trainingPhase={trainingPhase}
            />
          </React.Fragment>
        );
      })}

      {/* Loading overlay */}
      {loading && (
        <Box
          sx={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            bgcolor: 'rgba(255,255,255,0.7)', zIndex: 10,
          }}
        />
      )}
    </Paper>
  );
}
