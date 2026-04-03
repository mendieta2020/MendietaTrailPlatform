/**
 * HistorialPanel — PR-158
 *
 * Collapsible panel that shows a 6-week day-by-day workout history grid
 * above the Calendar week view. Includes repetition alerts and a [📋] copy
 * button per week row.
 *
 * Props:
 *   orgId         — organization ID
 *   teamId        — current team filter (or null for all)
 *   targetWeek    — Monday of the week being planned (YYYY-MM-DD)
 *   onCopyWeek    — callback(weekStart) when copy button is clicked
 *   loading       — external loading state (optional)
 */
import React, { useState, useEffect } from 'react';
import {
  Box, Typography, CircularProgress, Alert, Collapse, IconButton,
  Tooltip,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { getGroupWorkoutHistory } from '../api/planning';

const MONTHS_SHORT = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

function weekLabel(weekStart) {
  const d = new Date(weekStart + 'T12:00:00');
  const end = new Date(d);
  end.setDate(end.getDate() + 6);
  // ISO week number
  const copy = new Date(weekStart + 'T12:00:00');
  const dow = copy.getUTCDay() || 7;
  copy.setUTCDate(copy.getUTCDate() + 4 - dow);
  const yearStart = new Date(Date.UTC(copy.getUTCFullYear(), 0, 1));
  const wNum = Math.ceil(((copy - yearStart) / 86400000 + 1) / 7);
  return `W${wNum} (${d.getDate()} ${MONTHS_SHORT[d.getMonth()]})`;
}

export default function HistorialPanel({ orgId, teamId, targetWeek, onCopyWeek }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !orgId) return;
    let cancelled = false;
    getGroupWorkoutHistory(orgId, { weeks: 6, targetWeek, teamId: teamId || undefined })
      .then((res) => {
        if (!cancelled) { setData(res.data); setLoading(false); }
      })
      .catch(() => {
        if (!cancelled) { setError('Error cargando historial.'); setLoading(false); }
      });
    return () => { cancelled = true; };
  }, [open, orgId, teamId, targetWeek]);

  const weeks = data?.weeks ?? [];
  const alerts = data?.repetition_alerts ?? [];

  // Days of week header
  const DAY_COLS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];

  return (
    <Box
      sx={{
        mb: 1.5,
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 2,
        bgcolor: '#0f1621',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 0.75,
          cursor: 'pointer',
          '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' },
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            color: '#94a3b8',
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
            fontSize: '0.68rem',
          }}
        >
          Historial de grupo — últimas 6 semanas
        </Typography>
        <IconButton size="small" sx={{ color: '#94a3b8', p: 0.25 }}>
          {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        </IconButton>
      </Box>

      <Collapse in={open}>
        <Box sx={{ px: 2, pb: 1.5 }}>
          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
              <CircularProgress size={20} sx={{ color: '#F57C00' }} />
            </Box>
          )}

          {error && (
            <Alert severity="error" sx={{ fontSize: '0.72rem', py: 0.5 }}>{error}</Alert>
          )}

          {!loading && !error && weeks.length > 0 && (
            <>
              {/* Grid table */}
              <Box
                sx={{
                  overflowX: 'auto',
                  '&::-webkit-scrollbar': { height: 4 },
                  '&::-webkit-scrollbar-thumb': { bgcolor: '#334155', borderRadius: 2 },
                }}
              >
                <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '0.68rem' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', color: '#64748b', fontWeight: 700, padding: '4px 8px', minWidth: 80 }}>
                        SEMANA
                      </th>
                      {DAY_COLS.map((d) => (
                        <th key={d} style={{ textAlign: 'center', color: '#64748b', fontWeight: 700, padding: '4px 8px', minWidth: 70 }}>
                          {d}
                        </th>
                      ))}
                      <th style={{ width: 32 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {weeks.map((wk) => (
                      <tr
                        key={wk.week_start}
                        style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}
                      >
                        <td style={{ padding: '4px 8px', color: '#94a3b8', fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {weekLabel(wk.week_start)}
                        </td>
                        {wk.days.map((day) => (
                          <td key={day.date} style={{ padding: '4px 8px', verticalAlign: 'top' }}>
                            {day.workouts.length === 0 ? (
                              <span style={{ color: '#374151' }}>—</span>
                            ) : (
                              day.workouts.map((wo, i) => (
                                <div key={i} style={{ color: '#e2e8f0', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 100 }}>
                                  {wo.title}
                                </div>
                              ))
                            )}
                          </td>
                        ))}
                        <td style={{ padding: '4px 4px', textAlign: 'center' }}>
                          {wk.summary.sessions > 0 && onCopyWeek && (
                            <Tooltip title={`Copiar ${weekLabel(wk.week_start)} → semana actual`} placement="left">
                              <IconButton
                                size="small"
                                onClick={(e) => { e.stopPropagation(); onCopyWeek(wk.week_start); }}
                                sx={{ color: '#F57C00', p: 0.25 }}
                              >
                                <ContentCopyIcon sx={{ fontSize: 13 }} />
                              </IconButton>
                            </Tooltip>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Box>

              {/* Repetition alerts */}
              {alerts.length > 0 && (
                <Box sx={{ mt: 1 }}>
                  {alerts.map((a) => (
                    <Box
                      key={a.workout}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.75,
                        py: 0.25,
                        fontSize: '0.67rem',
                        color: a.severity === 'warning' ? '#fbbf24' : '#94a3b8',
                      }}
                    >
                      <span>{a.severity === 'warning' ? '⚠' : 'ℹ'}</span>
                      <span>
                        <strong>"{a.workout}"</strong> — {a.consecutive_weeks} semanas seguidas
                      </span>
                    </Box>
                  ))}
                </Box>
              )}
            </>
          )}

          {!loading && !error && weeks.length === 0 && (
            <Typography variant="caption" sx={{ color: '#4a5568', display: 'block', py: 1 }}>
              Sin historial disponible para este grupo.
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
