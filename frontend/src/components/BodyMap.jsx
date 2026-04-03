/**
 * BodyMap.jsx — PR-161
 * Interactive body map using react-body-highlighter.
 * Zones map to AthleteInjury.body_zone choices.
 *
 * Props:
 *   injuries   – array of AthleteInjury objects (body_zone + severity + status)
 *   onZoneClick(zone) – called when a muscle/zone is clicked (readOnly=false only)
 *   readOnly   – boolean (default false)
 */
import React, { useState } from 'react';
import { Box, ToggleButton, ToggleButtonGroup } from '@mui/material';
import Model from 'react-body-highlighter';

const MUSCLE = {
  TRAPEZIUS: 'trapezius',
  UPPER_BACK: 'upper-back',
  LOWER_BACK: 'lower-back',
  CHEST: 'chest',
  BICEPS: 'biceps',
  TRICEPS: 'triceps',
  FOREARM: 'forearm',
  BACK_DELTOIDS: 'back-deltoids',
  FRONT_DELTOIDS: 'front-deltoids',
  ABS: 'abs',
  OBLIQUES: 'obliques',
  ABDUCTORS: 'abductors',
  HAMSTRING: 'hamstring',
  QUADRICEPS: 'quadriceps',
  CALVES: 'calves',
  GLUTEAL: 'gluteal',
  HEAD: 'head',
  NECK: 'neck',
  KNEES: 'knees',
  LEFT_SOLEUS: 'left-soleus',
  RIGHT_SOLEUS: 'right-soleus',
};

const ZONE_TO_MUSCLES = {
  cabeza:         [MUSCLE.HEAD],
  cuello:         [MUSCLE.NECK],
  hombro:         [MUSCLE.FRONT_DELTOIDS, MUSCLE.BACK_DELTOIDS, MUSCLE.TRAPEZIUS],
  brazo:          [MUSCLE.BICEPS, MUSCLE.TRICEPS],
  codo:           [MUSCLE.BICEPS],
  muneca:         [MUSCLE.FOREARM],
  mano:           [MUSCLE.FOREARM],
  pecho:          [MUSCLE.CHEST, MUSCLE.ABS],
  espalda_alta:   [MUSCLE.UPPER_BACK, MUSCLE.TRAPEZIUS, MUSCLE.BACK_DELTOIDS],
  espalda_baja:   [MUSCLE.LOWER_BACK],
  cadera:         [MUSCLE.OBLIQUES, MUSCLE.ABDUCTORS],
  muslo:          [MUSCLE.QUADRICEPS],
  rodilla:        [MUSCLE.KNEES],
  pantorrilla:    [MUSCLE.CALVES],
  espinilla:      [MUSCLE.QUADRICEPS],
  tobillo:        [MUSCLE.LEFT_SOLEUS, MUSCLE.RIGHT_SOLEUS],
  pie:            [MUSCLE.LEFT_SOLEUS, MUSCLE.RIGHT_SOLEUS],
  gluteo:         [MUSCLE.GLUTEAL],
  isquiotibial:   [MUSCLE.HAMSTRING],
  talon:          [MUSCLE.CALVES],
  planta_del_pie: [MUSCLE.LEFT_SOLEUS, MUSCLE.RIGHT_SOLEUS],
};

const MUSCLE_TO_ZONE = {};
Object.entries(ZONE_TO_MUSCLES).forEach(([zone, muscles]) => {
  muscles.forEach(m => { if (!MUSCLE_TO_ZONE[m]) MUSCLE_TO_ZONE[m] = zone; });
});

const SEVERITY_FREQ = { leve: 1, moderada: 2, severa: 3 };
const HIGHLIGHT_COLORS = ['#FCD34D', '#F97316', '#EF4444'];

function buildModelData(injuries) {
  const zoneMap = {};
  (injuries || []).forEach(inj => {
    if (inj.status === 'resuelta') return;
    const zone = inj.body_zone;
    const freq = SEVERITY_FREQ[inj.severity] ?? 1;
    if (!zoneMap[zone] || freq > zoneMap[zone].freq) {
      zoneMap[zone] = { freq, inj };
    }
  });
  return Object.entries(zoneMap).map(([zone, { freq }]) => ({
    name: zone,
    muscles: ZONE_TO_MUSCLES[zone] ?? [],
    frequency: freq,
  }));
}

export function BodyMap({ injuries = [], onZoneClick, readOnly = false }) {
  const [view, setView] = useState('anterior');
  const modelData = buildModelData(injuries);

  const handleClick = readOnly ? undefined : (muscleStats) => {
    if (!muscleStats?.muscle || !onZoneClick) return;
    const zone = MUSCLE_TO_ZONE[muscleStats.muscle];
    if (zone) onZoneClick(zone);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
      <ToggleButtonGroup
        value={view}
        exclusive
        onChange={(_, v) => { if (v) setView(v); }}
        size="small"
      >
        <ToggleButton value="anterior" sx={{ fontSize: '0.68rem', px: 1.5, py: 0.3, textTransform: 'none' }}>
          Frontal
        </ToggleButton>
        <ToggleButton value="posterior" sx={{ fontSize: '0.68rem', px: 1.5, py: 0.3, textTransform: 'none' }}>
          Trasera
        </ToggleButton>
      </ToggleButtonGroup>

      <Box sx={{
        bgcolor: '#0f172a',
        borderRadius: 2,
        p: 1.5,
        display: 'flex',
        justifyContent: 'center',
      }}>
        <Model
          type={view}
          data={modelData}
          bodyColor="#1e293b"
          highlightedColors={HIGHLIGHT_COLORS}
          onClick={handleClick}
          svgStyle={{ maxHeight: 220, cursor: readOnly ? 'default' : 'pointer' }}
        />
      </Box>
    </Box>
  );
}

export default BodyMap;
