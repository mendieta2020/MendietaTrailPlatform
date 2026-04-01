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
const ZONE_FILL_DEFAULT = '#E2E8F0';
const ZONE_FILL_HOVER   = '#C7D2FE';

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
    strokeWidth: 0.8,
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
// Organic shapes at viewBox "0 0 110 270"
const FRONT_ZONES = [
  // Head
  { zone: 'cabeza',      isCircle: true, cx: 55, cy: 20, r: 14,  display: 'Cabeza' },
  // Neck
  { zone: 'cuello',      d: 'M49,34 Q46,38 47,43 L63,43 Q64,38 61,34 Z', display: 'Cuello' },
  // Shoulders (bilateral — both click same zone)
  { zone: 'hombro',      d: 'M22,44 Q17,47 15,57 L15,71 Q20,74 28,72 L30,54 Q27,49 22,44 Z', display: 'Hombro' },
  { zone: 'hombro',      d: 'M88,44 Q93,47 95,57 L95,71 Q90,74 82,72 L80,54 Q83,49 88,44 Z', display: 'Hombro' },
  // Chest
  { zone: 'pecho',       d: 'M30,44 Q26,56 27,72 L27,79 L83,79 L83,72 Q84,56 80,44 Q68,41 55,41 Q42,41 30,44 Z', display: 'Pecho' },
  // Upper arms
  { zone: 'brazo',       d: 'M14,71 Q9,76 9,92 L12,109 Q15,111 22,110 L23,73 Z', display: 'Brazo' },
  { zone: 'brazo',       d: 'M96,71 Q101,76 101,92 L98,109 Q95,111 88,110 L87,73 Z', display: 'Brazo' },
  // Elbows
  { zone: 'codo',        isCircle: true, cx: 14, cy: 112, r: 6, display: 'Codo' },
  { zone: 'codo',        isCircle: true, cx: 96, cy: 112, r: 6, display: 'Codo' },
  // Wrists
  { zone: 'muneca',      d: 'M10,119 L24,119 L24,127 L10,127 Z', display: 'Muñeca' },
  { zone: 'muneca',      d: 'M86,119 L100,119 L100,127 L86,127 Z', display: 'Muñeca' },
  // Hands
  { zone: 'mano',        d: 'M9,127 L25,127 L25,141 L9,141 Z', display: 'Mano' },
  { zone: 'mano',        d: 'M85,127 L101,127 L101,141 L85,141 Z', display: 'Mano' },
  // Core / hip
  { zone: 'cadera',      d: 'M27,79 Q24,91 27,108 L33,119 L77,119 L83,108 Q86,91 83,79 Z', display: 'Cadera' },
  // Quadriceps (front thigh)
  { zone: 'muslo',       d: 'M33,119 Q27,127 27,145 L28,172 Q33,179 43,178 L44,121 Q39,119 33,119 Z', display: 'Muslo/Cuádr.' },
  { zone: 'muslo',       d: 'M77,119 Q83,127 83,145 L82,172 Q77,179 67,178 L66,121 Q71,119 77,119 Z', display: 'Muslo/Cuádr.' },
  // Knees
  { zone: 'rodilla',     isCircle: true, cx: 38, cy: 181, r: 8, display: 'Rodilla' },
  { zone: 'rodilla',     isCircle: true, cx: 72, cy: 181, r: 8, display: 'Rodilla' },
  // Shins (espinilla — front of lower leg)
  { zone: 'espinilla',   d: 'M29,189 L47,189 L46,224 L30,224 Z', display: 'Espinilla' },
  { zone: 'espinilla',   d: 'M63,189 L81,189 L80,224 L64,224 Z', display: 'Espinilla' },
  // Ankles
  { zone: 'tobillo',     d: 'M28,224 L48,224 L48,234 L28,234 Z', display: 'Tobillo' },
  { zone: 'tobillo',     d: 'M62,224 L82,224 L82,234 L62,234 Z', display: 'Tobillo' },
  // Feet (top)
  { zone: 'pie',         d: 'M24,234 L48,234 L52,249 L20,249 Z', display: 'Pie' },
  { zone: 'pie',         d: 'M62,234 L86,234 L90,249 L58,249 Z', display: 'Pie' },
];

// ── Back-view zone definitions ───────────────────────────────────────────────
const BACK_ZONES = [
  { zone: 'cabeza',        isCircle: true, cx: 55, cy: 20, r: 14, display: 'Cabeza' },
  { zone: 'cuello',        d: 'M49,34 Q46,38 47,43 L63,43 Q64,38 61,34 Z', display: 'Cuello' },
  // Shoulders
  { zone: 'hombro',        d: 'M22,44 Q17,47 15,57 L15,71 Q20,74 28,72 L30,54 Q27,49 22,44 Z', display: 'Hombro' },
  { zone: 'hombro',        d: 'M88,44 Q93,47 95,57 L95,71 Q90,74 82,72 L80,54 Q83,49 88,44 Z', display: 'Hombro' },
  // Upper back (same outer shape as chest)
  { zone: 'espalda_alta',  d: 'M30,44 Q26,56 27,72 L27,79 L83,79 L83,72 Q84,56 80,44 Q68,41 55,41 Q42,41 30,44 Z', display: 'Espalda alta' },
  // Lower back
  { zone: 'espalda_baja',  d: 'M27,79 Q24,88 26,100 L27,110 L83,110 L84,100 Q86,88 83,79 Z', display: 'Espalda baja' },
  // Arms
  { zone: 'brazo',         d: 'M14,71 Q9,76 9,92 L12,109 Q15,111 22,110 L23,73 Z', display: 'Brazo' },
  { zone: 'brazo',         d: 'M96,71 Q101,76 101,92 L98,109 Q95,111 88,110 L87,73 Z', display: 'Brazo' },
  { zone: 'codo',          isCircle: true, cx: 14, cy: 112, r: 6, display: 'Codo' },
  { zone: 'codo',          isCircle: true, cx: 96, cy: 112, r: 6, display: 'Codo' },
  { zone: 'muneca',        d: 'M10,119 L24,119 L24,127 L10,127 Z', display: 'Muñeca' },
  { zone: 'muneca',        d: 'M86,119 L100,119 L100,127 L86,127 Z', display: 'Muñeca' },
  { zone: 'mano',          d: 'M9,127 L25,127 L25,141 L9,141 Z', display: 'Mano' },
  { zone: 'mano',          d: 'M85,127 L101,127 L101,141 L85,141 Z', display: 'Mano' },
  // Glutes
  { zone: 'gluteo',        d: 'M27,110 Q22,114 22,124 Q22,134 29,141 Q37,148 55,148 Q73,148 81,141 Q88,134 88,124 Q88,114 83,110 Z', display: 'Glúteos' },
  // Hamstrings
  { zone: 'isquiotibial',  d: 'M29,141 Q23,150 23,165 L26,172 Q32,179 43,178 L44,143 Q37,140 29,141 Z', display: 'Isquiotibial' },
  { zone: 'isquiotibial',  d: 'M81,141 Q87,150 87,165 L84,172 Q78,179 67,178 L66,143 Q73,140 81,141 Z', display: 'Isquiotibial' },
  { zone: 'rodilla',       isCircle: true, cx: 38, cy: 181, r: 8, display: 'Rodilla' },
  { zone: 'rodilla',       isCircle: true, cx: 72, cy: 181, r: 8, display: 'Rodilla' },
  // Calves (back of lower leg)
  { zone: 'pantorrilla',   d: 'M29,189 L47,189 L46,224 L30,224 Z', display: 'Pantorrilla' },
  { zone: 'pantorrilla',   d: 'M63,189 L81,189 L80,224 L64,224 Z', display: 'Pantorrilla' },
  // Heels
  { zone: 'talon',         d: 'M28,224 L48,224 L48,234 L28,234 Z', display: 'Talón' },
  { zone: 'talon',         d: 'M62,224 L82,224 L82,234 L62,234 Z', display: 'Talón' },
  // Soles
  { zone: 'planta_del_pie', d: 'M24,234 L48,234 L52,249 L20,249 Z', display: 'Planta del pie' },
  { zone: 'planta_del_pie', d: 'M62,234 L86,234 L90,249 L58,249 Z', display: 'Planta del pie' },
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
        viewBox="0 0 110 270"
        width="110"
        height="270"
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
