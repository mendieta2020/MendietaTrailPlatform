/**
 * BodyMap.jsx
 * Interactive SVG body figure — front and back views.
 * Zones map to AthleteInjury.body_zone choices.
 *
 * Props:
 *   injuries   – array of AthleteInjury objects (body_zone + severity + status)
 *   onZoneClick(zone) – called when a zone is clicked (readOnly=false only)
 *   readOnly   – boolean (default false)
 */

import React, { useState } from 'react';
import { Tooltip, Box, ToggleButton, ToggleButtonGroup } from '@mui/material';

const SEVERITY_FILL = {
  leve:     '#FCD34D',
  moderada: '#F97316',
  severa:   '#EF4444',
};
const ZONE_FILL_DEFAULT = '#CBD5E1';
const ZONE_FILL_HOVER   = '#A5B4FC';

function buildZoneMap(injuries) {
  const map = {};
  (injuries || []).forEach((inj) => {
    if (inj.status === 'resuelta') return;
    const zone = inj.body_zone;
    const priority = { severa: 3, moderada: 2, leve: 1 };
    const current = map[zone];
    if (!current || (priority[inj.severity] ?? 0) > (priority[current.severity] ?? 0)) {
      map[zone] = inj;
    }
  });
  return map;
}

function Zone({ isCircle, d, cx, cy, r, fill, label, onClick, readOnly }) {
  const [hovered, setHovered] = React.useState(false);
  const color = hovered && !readOnly ? ZONE_FILL_HOVER : fill;
  const sharedProps = {
    fill: color,
    stroke: '#94A3B8',
    strokeWidth: 0.6,
    style: { cursor: readOnly ? 'default' : 'pointer', transition: 'fill 0.15s' },
    onClick: readOnly ? undefined : onClick,
    onMouseEnter: () => setHovered(true),
    onMouseLeave: () => setHovered(false),
  };
  return (
    <Tooltip title={label} placement="right" arrow>
      {isCircle
        ? <circle cx={cx} cy={cy} r={r} {...sharedProps} />
        : <path d={d} {...sharedProps} />
      }
    </Tooltip>
  );
}

// ── Front-view zone definitions ──────────────────────────────────────────────
// Organic humanized shapes — viewBox "0 0 120 290"
// Origin: top-center. Head center ~(60,18).
const FRONT_ZONES = [
  // Head — slightly oval
  { zone: 'cabeza',
    d: 'M60,4 C72,4 80,10 80,20 C80,32 72,36 60,36 C48,36 40,32 40,20 C40,10 48,4 60,4 Z',
    display: 'Cabeza' },

  // Neck — narrow trapezoid with gentle curves
  { zone: 'cuello',
    d: 'M53,36 C51,38 50,41 51,45 L69,45 C70,41 69,38 67,36 Z',
    display: 'Cuello' },

  // Left shoulder (viewer's right) — rounded bump
  { zone: 'hombro',
    d: 'M51,45 C44,44 34,44 26,50 C20,55 18,63 20,72 C24,74 30,73 34,71 L36,58 C40,52 46,47 51,45 Z',
    display: 'Hombro' },

  // Right shoulder (viewer's left)
  { zone: 'hombro',
    d: 'M69,45 C76,44 86,44 94,50 C100,55 102,63 100,72 C96,74 90,73 86,71 L84,58 C80,52 74,47 69,45 Z',
    display: 'Hombro' },

  // Chest / torso — with gentle waist taper
  { zone: 'pecho',
    d: 'M34,50 C32,58 31,68 32,78 C33,86 35,92 36,100 C40,101 50,102 60,102 C70,102 80,101 84,100 C85,92 87,86 88,78 C89,68 88,58 86,50 C78,46 70,44 60,44 C50,44 42,46 34,50 Z',
    display: 'Pecho' },

  // Left upper arm
  { zone: 'brazo',
    d: 'M20,72 C15,78 12,88 12,100 L15,116 C18,118 24,117 27,115 L27,73 C25,72 22,72 20,72 Z',
    display: 'Brazo' },

  // Right upper arm
  { zone: 'brazo',
    d: 'M100,72 C105,78 108,88 108,100 L105,116 C102,118 96,117 93,115 L93,73 C95,72 98,72 100,72 Z',
    display: 'Brazo' },

  // Left elbow
  { zone: 'codo', isCircle: true, cx: 16, cy: 119, r: 6, display: 'Codo' },
  // Right elbow
  { zone: 'codo', isCircle: true, cx: 104, cy: 119, r: 6, display: 'Codo' },

  // Left forearm / wrist zone (combined for readability)
  { zone: 'muneca',
    d: 'M11,125 C10,128 10,133 11,137 L23,137 C24,133 24,128 23,125 Z',
    display: 'Muñeca' },
  { zone: 'muneca',
    d: 'M97,125 C96,128 96,133 97,137 L109,137 C110,133 110,128 109,125 Z',
    display: 'Muñeca' },

  // Hands
  { zone: 'mano',
    d: 'M10,137 C8,140 8,148 10,152 L24,152 C26,148 26,140 24,137 Z',
    display: 'Mano' },
  { zone: 'mano',
    d: 'M96,137 C94,140 94,148 96,152 L110,152 C112,148 112,140 110,137 Z',
    display: 'Mano' },

  // Abdomen / hip — wider hips taper from waist
  { zone: 'cadera',
    d: 'M36,100 C33,112 32,124 34,134 L38,142 L82,142 L86,134 C88,124 87,112 84,100 C76,103 68,104 60,104 C52,104 44,103 36,100 Z',
    display: 'Cadera' },

  // Left quad (front thigh)
  { zone: 'muslo',
    d: 'M38,142 C33,150 31,162 32,176 L34,190 C38,194 46,194 50,191 L50,143 C46,142 42,142 38,142 Z',
    display: 'Muslo/Cuádr.' },
  // Right quad
  { zone: 'muslo',
    d: 'M82,142 C87,150 89,162 88,176 L86,190 C82,194 74,194 70,191 L70,143 C74,142 78,142 82,142 Z',
    display: 'Muslo/Cuádr.' },

  // Left knee
  { zone: 'rodilla', isCircle: true, cx: 41, cy: 194, r: 9, display: 'Rodilla' },
  // Right knee
  { zone: 'rodilla', isCircle: true, cx: 79, cy: 194, r: 9, display: 'Rodilla' },

  // Left shin (espinilla — front lower leg)
  { zone: 'espinilla',
    d: 'M34,203 C32,212 32,224 34,236 L49,236 C50,224 50,212 48,203 Z',
    display: 'Espinilla' },
  // Right shin
  { zone: 'espinilla',
    d: 'M72,203 C70,212 70,224 72,236 L87,236 C88,224 88,212 86,203 Z',
    display: 'Espinilla' },

  // Left ankle
  { zone: 'tobillo',
    d: 'M33,236 C32,240 32,245 34,248 L50,248 C51,245 51,240 50,236 Z',
    display: 'Tobillo' },
  // Right ankle
  { zone: 'tobillo',
    d: 'M71,236 C70,240 70,245 72,248 L88,248 C89,245 89,240 88,236 Z',
    display: 'Tobillo' },

  // Left foot (top view)
  { zone: 'pie',
    d: 'M30,248 C26,250 22,256 24,262 L52,262 C54,256 53,250 50,248 Z',
    display: 'Pie' },
  // Right foot
  { zone: 'pie',
    d: 'M70,248 C68,250 67,256 69,262 L97,262 C99,256 95,250 91,248 Z',
    display: 'Pie' },
];

// ── Back-view zone definitions ───────────────────────────────────────────────
const BACK_ZONES = [
  // Head
  { zone: 'cabeza',
    d: 'M60,4 C72,4 80,10 80,20 C80,32 72,36 60,36 C48,36 40,32 40,20 C40,10 48,4 60,4 Z',
    display: 'Cabeza' },

  // Neck
  { zone: 'cuello',
    d: 'M53,36 C51,38 50,41 51,45 L69,45 C70,41 69,38 67,36 Z',
    display: 'Cuello' },

  // Shoulders
  { zone: 'hombro',
    d: 'M51,45 C44,44 34,44 26,50 C20,55 18,63 20,72 C24,74 30,73 34,71 L36,58 C40,52 46,47 51,45 Z',
    display: 'Hombro' },
  { zone: 'hombro',
    d: 'M69,45 C76,44 86,44 94,50 C100,55 102,63 100,72 C96,74 90,73 86,71 L84,58 C80,52 74,47 69,45 Z',
    display: 'Hombro' },

  // Upper back (trapezius / upper back muscles)
  { zone: 'espalda_alta',
    d: 'M34,50 C32,60 31,70 32,80 C40,82 50,83 60,83 C70,83 80,82 88,80 C89,70 88,60 86,50 C78,46 70,44 60,44 C50,44 42,46 34,50 Z',
    display: 'Espalda alta' },

  // Lower back (lumbar)
  { zone: 'espalda_baja',
    d: 'M32,80 C31,90 32,102 34,112 L86,112 C88,102 89,90 88,80 C80,82 70,83 60,83 C50,83 40,82 32,80 Z',
    display: 'Espalda baja' },

  // Arms (same as front)
  { zone: 'brazo',
    d: 'M20,72 C15,78 12,88 12,100 L15,116 C18,118 24,117 27,115 L27,73 C25,72 22,72 20,72 Z',
    display: 'Brazo' },
  { zone: 'brazo',
    d: 'M100,72 C105,78 108,88 108,100 L105,116 C102,118 96,117 93,115 L93,73 C95,72 98,72 100,72 Z',
    display: 'Brazo' },

  { zone: 'codo', isCircle: true, cx: 16, cy: 119, r: 6, display: 'Codo' },
  { zone: 'codo', isCircle: true, cx: 104, cy: 119, r: 6, display: 'Codo' },

  { zone: 'muneca',
    d: 'M11,125 C10,128 10,133 11,137 L23,137 C24,133 24,128 23,125 Z',
    display: 'Muñeca' },
  { zone: 'muneca',
    d: 'M97,125 C96,128 96,133 97,137 L109,137 C110,133 110,128 109,125 Z',
    display: 'Muñeca' },

  { zone: 'mano',
    d: 'M10,137 C8,140 8,148 10,152 L24,152 C26,148 26,140 24,137 Z',
    display: 'Mano' },
  { zone: 'mano',
    d: 'M96,137 C94,140 94,148 96,152 L110,152 C112,148 112,140 110,137 Z',
    display: 'Mano' },

  // Glutes — wide, rounded
  { zone: 'gluteo',
    d: 'M34,112 C28,116 24,124 26,134 C28,144 38,152 60,152 C82,152 92,144 94,134 C96,124 92,116 86,112 Z',
    display: 'Glúteos' },

  // Hamstrings
  { zone: 'isquiotibial',
    d: 'M34,152 C29,160 27,172 28,186 L32,196 C36,200 44,200 48,197 L50,153 C44,152 38,152 34,152 Z',
    display: 'Isquiotibial' },
  { zone: 'isquiotibial',
    d: 'M86,152 C91,160 93,172 92,186 L88,196 C84,200 76,200 72,197 L70,153 C76,152 82,152 86,152 Z',
    display: 'Isquiotibial' },

  { zone: 'rodilla', isCircle: true, cx: 41, cy: 200, r: 9, display: 'Rodilla' },
  { zone: 'rodilla', isCircle: true, cx: 79, cy: 200, r: 9, display: 'Rodilla' },

  // Calves
  { zone: 'pantorrilla',
    d: 'M34,209 C31,220 31,232 34,242 L50,242 C52,232 52,220 49,209 Z',
    display: 'Pantorrilla' },
  { zone: 'pantorrilla',
    d: 'M72,209 C70,220 70,232 72,242 L88,242 C90,232 90,220 87,209 Z',
    display: 'Pantorrilla' },

  // Heels
  { zone: 'talon',
    d: 'M33,242 C31,246 31,252 34,255 L50,255 C52,252 52,246 50,242 Z',
    display: 'Talón' },
  { zone: 'talon',
    d: 'M71,242 C70,246 70,252 72,255 L88,255 C90,252 90,246 88,242 Z',
    display: 'Talón' },

  // Soles
  { zone: 'planta_del_pie',
    d: 'M30,255 C26,257 22,262 24,268 L52,268 C54,262 53,257 50,255 Z',
    display: 'Planta del pie' },
  { zone: 'planta_del_pie',
    d: 'M70,255 C68,257 67,262 69,268 L97,268 C99,262 95,257 91,255 Z',
    display: 'Planta del pie' },
];

export function BodyMap({ injuries = [], onZoneClick, readOnly = false }) {
  const [view, setView] = useState('front');
  const zoneMap = buildZoneMap(injuries);

  const fill = (zone) => {
    const inj = zoneMap[zone];
    return inj ? (SEVERITY_FILL[inj.severity] ?? ZONE_FILL_DEFAULT) : ZONE_FILL_DEFAULT;
  };

  const label = (zone, display) => {
    const inj = zoneMap[zone];
    return inj ? `${display} — ${inj.severity} (${inj.status})` : display;
  };

  const click = (zone) => () => { if (!readOnly && onZoneClick) onZoneClick(zone); };

  const zones = view === 'front' ? FRONT_ZONES : BACK_ZONES;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
      <ToggleButtonGroup
        value={view}
        exclusive
        onChange={(_, v) => { if (v) setView(v); }}
        size="small"
      >
        <ToggleButton value="front" sx={{ fontSize: '0.68rem', px: 1.5, py: 0.3, textTransform: 'none' }}>
          Frontal
        </ToggleButton>
        <ToggleButton value="back" sx={{ fontSize: '0.68rem', px: 1.5, py: 0.3, textTransform: 'none' }}>
          Trasera
        </ToggleButton>
      </ToggleButtonGroup>

      <svg
        viewBox="0 0 120 280"
        width="120"
        height="280"
        xmlns="http://www.w3.org/2000/svg"
        aria-label={`Mapa corporal — vista ${view === 'front' ? 'frontal' : 'trasera'}`}
      >
        {zones.map((z, i) => (
          <Zone
            key={`${z.zone}-${i}`}
            isCircle={z.isCircle}
            cx={z.cx} cy={z.cy} r={z.r}
            d={z.d}
            fill={fill(z.zone)}
            label={label(z.zone, z.display)}
            onClick={click(z.zone)}
            readOnly={readOnly}
          />
        ))}
      </svg>
    </Box>
  );
}

export default BodyMap;
