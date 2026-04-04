/**
 * WellnessCheckIn.jsx
 * Daily wellness check-in modal overlay.
 *
 * Shows once per day (if athlete hasn't answered today and hasn't dismissed).
 * "No me preguntes más" shows a confirmation screen before permanently dismissing.
 *
 * Props:
 *   firstName   – athlete first name
 *   orgId       – organization ID
 *   athleteId   – athlete ID
 *   onDismissSession  – called after saving or skipping for today (hide overlay)
 */

import React, { useState } from 'react';
import { Box, Typography, Paper, Button } from '@mui/material';
import { submitWellnessCheckIn, dismissWellnessPrompt } from '../api/p1';

const DIMENSIONS = [
  { key: 'sleep_quality',   label: 'Sueño',       emoji: '😴', low: 'Muy malo', high: 'Excelente' },
  { key: 'mood',            label: 'Ánimo',        emoji: '😊', low: 'Muy bajo', high: 'Excelente' },
  { key: 'energy',          label: 'Energía',      emoji: '⚡',  low: 'Sin energía', high: 'Con mucha' },
  { key: 'muscle_soreness', label: 'Dolores musc.', emoji: '💪', low: 'Muy dolorido', high: 'Sin dolor' },
  { key: 'stress',          label: 'Estrés',       emoji: '🧘', low: 'Muy estresado', high: 'Muy relajado' },
];

const DOT_COLORS = ['#EF4444', '#F97316', '#F59E0B', '#84CC16', '#00D4AA'];

function ScoreInput({ dimension, value, onChange }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <span style={{ fontSize: '1.1rem' }}>{dimension.emoji}</span>
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#1E293B' }}>
            {dimension.label}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {[1, 2, 3, 4, 5].map((v) => (
            <Box
              key={v}
              onClick={() => onChange(v)}
              sx={{
                width: 28, height: 28, borderRadius: '50%',
                bgcolor: value >= v ? DOT_COLORS[v - 1] : '#E2E8F0',
                cursor: 'pointer',
                border: value === v ? `2px solid ${DOT_COLORS[v - 1]}` : '2px solid transparent',
                transition: 'background-color 0.15s',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            />
          ))}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Typography variant="caption" sx={{ color: '#94A3B8', fontSize: '0.65rem' }}>
          {dimension.low}
        </Typography>
        <Typography variant="caption" sx={{ color: '#94A3B8', fontSize: '0.65rem' }}>
          {dimension.high}
        </Typography>
      </Box>
    </Box>
  );
}

export function WellnessCheckIn({ firstName, orgId, athleteId, onDismissSession }) {
  const [scores, setScores] = useState({ sleep_quality: 3, mood: 3, energy: 3, muscle_soreness: 3, stress: 3 });
  const [saving, setSaving] = useState(false);
  const [phase, setPhase] = useState('checkin'); // 'checkin' | 'dismiss-confirm'

  const handleScore = (key, val) => setScores((p) => ({ ...p, [key]: val }));

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await submitWellnessCheckIn(orgId, athleteId, scores);
    } catch {
      // best-effort — don't block the athlete on API error
    } finally {
      setSaving(false);
      onDismissSession();
    }
  };

  const handlePermanentDismiss = async () => {
    try {
      await dismissWellnessPrompt(orgId, athleteId);
    } catch {
      // best-effort
    }
    onDismissSession();
  };

  if (phase === 'dismiss-confirm') {
    return (
      <Paper sx={{
        p: 4, borderRadius: 4, maxWidth: 420, width: '100%',
        background: 'linear-gradient(135deg, #FFF7ED 0%, #FFFBEB 100%)',
        border: '1px solid #FED7AA',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
      }}>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#92400E', mb: 1.5 }}>
          ¿Seguro que querés desactivarlo?
        </Typography>
        <Typography variant="body2" sx={{ color: '#78350F', mb: 2, lineHeight: 1.6 }}>
          Estos datos ayudan a tu coach a <strong>prevenir lesiones</strong> y ajustar
          la carga de entrenamiento. La UEFA lo considera la herramienta #2 para
          prevención de lesiones.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5, flexDirection: 'column' }}>
          <Button
            variant="contained"
            fullWidth
            onClick={() => setPhase('checkin')}
            sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#059669' }, borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
            Seguir contestando
          </Button>
          <Button
            variant="text"
            fullWidth
            onClick={handlePermanentDismiss}
            sx={{ color: '#9CA3AF', textTransform: 'none', fontSize: '0.82rem' }}>
            Desactivar de todas formas →
          </Button>
        </Box>
      </Paper>
    );
  }

  return (
    <Paper sx={{
      p: 4, borderRadius: 4, maxWidth: 420, width: '100%',
      background: 'linear-gradient(135deg, #EEF2FF 0%, #F0FDF4 100%)',
      border: '1px solid #C7D2FE',
      boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
    }}>
      <Typography variant="h6" sx={{ fontWeight: 700, color: '#1E293B', mb: 0.5 }}>
        ☀️ Buenos días, {firstName}
      </Typography>
      <Typography variant="body2" sx={{ color: '#475569', mb: 3 }}>
        ¿Cómo te sentís hoy? (1 min)
      </Typography>

      {DIMENSIONS.map((dim) => (
        <ScoreInput
          key={dim.key}
          dimension={dim}
          value={scores[dim.key]}
          onChange={(v) => handleScore(dim.key, v)}
        />
      ))}

      <Button
        variant="contained"
        fullWidth
        onClick={handleSubmit}
        disabled={saving}
        sx={{
          mt: 2, bgcolor: '#6366F1', '&:hover': { bgcolor: '#4F46E5' },
          borderRadius: 2, textTransform: 'none', fontWeight: 700, py: 1.4,
        }}>
        {saving ? 'Enviando…' : 'Enviar →'}
      </Button>

      <Box sx={{ textAlign: 'center', mt: 1.5 }}>
        <Button
          variant="text"
          size="small"
          onClick={() => setPhase('dismiss-confirm')}
          sx={{ color: '#94A3B8', textTransform: 'none', fontSize: '0.78rem' }}>
          No me preguntes más →
        </Button>
      </Box>
    </Paper>
  );
}

export default WellnessCheckIn;
