/**
 * BodyMap.jsx
 * Interactive SVG figure of the human body (frontal view).
 * Each zone maps to AthleteInjury.body_zone choices.
 *
 * Props:
 *   injuries   – array of AthleteInjury objects (with body_zone + severity + status)
 *   onZoneClick(zone) – called when a zone is clicked (readOnly=false only)
 *   readOnly   – boolean (default false). If true, zones are display-only.
 */

import React from 'react';
import { Tooltip } from '@mui/material';

const SEVERITY_FILL = {
  leve:     '#FCD34D',
  moderada: '#F97316',
  severa:   '#EF4444',
};

const ZONE_FILL_DEFAULT = '#E2E8F0';
const ZONE_FILL_HOVER   = '#C7D2FE';

// Build a zone → highest severity map from active injuries
function buildZoneMap(injuries) {
  const map = {};
  (injuries || []).forEach((inj) => {
    if (inj.status === 'resuelta') return;
    const zone = inj.body_zone;
    const current = map[zone];
    const priority = { severa: 3, moderada: 2, leve: 1 };
    if (!current || (priority[inj.severity] ?? 0) > (priority[current.severity] ?? 0)) {
      map[zone] = inj;
    }
  });
  return map;
}

// Individual SVG zone path
function Zone({ d, cx, cy, r, isCircle, fill, label, onClick, readOnly }) {
  const [hovered, setHovered] = React.useState(false);
  const color = hovered && !readOnly ? ZONE_FILL_HOVER : fill;
  const props = {
    fill: color,
    stroke: '#94A3B8',
    strokeWidth: 1,
    style: { cursor: readOnly ? 'default' : 'pointer', transition: 'fill 0.15s' },
    onClick: readOnly ? undefined : onClick,
    onMouseEnter: () => setHovered(true),
    onMouseLeave: () => setHovered(false),
  };
  return (
    <Tooltip title={label} placement="right" arrow>
      {isCircle
        ? <circle cx={cx} cy={cy} r={r} {...props} />
        : <path d={d} {...props} />
      }
    </Tooltip>
  );
}

/**
 * Minimalist SVG body figure at 120×280 viewport.
 * Zones are coarse shapes mapped to AthleteInjury.BodyZone choices.
 */
export function BodyMap({ injuries = [], onZoneClick, readOnly = false }) {
  const zoneMap = buildZoneMap(injuries);

  const fill = (zone) => {
    const inj = zoneMap[zone];
    return inj ? (SEVERITY_FILL[inj.severity] ?? ZONE_FILL_DEFAULT) : ZONE_FILL_DEFAULT;
  };

  const label = (zone, display) => {
    const inj = zoneMap[zone];
    if (inj) return `${display} — ${inj.severity} (${inj.status})`;
    return display;
  };

  const click = (zone) => () => { if (!readOnly && onZoneClick) onZoneClick(zone); };

  return (
    <svg
      viewBox="0 0 120 280"
      width="120"
      height="280"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Mapa corporal"
    >
      {/* ── Head ── */}
      <Zone id="cabeza" isCircle cx={60} cy={20} r={16}
        fill={fill('cabeza')} label={label('cabeza', 'Cabeza')}
        onClick={click('cabeza')} readOnly={readOnly} />

      {/* ── Neck ── */}
      <Zone id="cuello" d="M54,36 L66,36 L66,46 L54,46 Z"
        fill={fill('cuello')} label={label('cuello', 'Cuello')}
        onClick={click('cuello')} readOnly={readOnly} />

      {/* ── Chest (upper torso) ── */}
      <Zone id="pecho" d="M38,46 L82,46 L80,90 L40,90 Z"
        fill={fill('pecho')} label={label('pecho', 'Pecho')}
        onClick={click('pecho')} readOnly={readOnly} />

      {/* ── Upper back (shown on front as shoulder blades hint) ── */}
      <Zone id="espalda_alta" d="M40,46 L38,46 L30,52 L30,80 L40,85 Z"
        fill={fill('espalda_alta')} label={label('espalda_alta', 'Espalda alta')}
        onClick={click('espalda_alta')} readOnly={readOnly} />
      <Zone id="espalda_alta_r" d="M80,46 L82,46 L90,52 L90,80 L80,85 Z"
        fill={fill('espalda_alta')} label={label('espalda_alta', 'Espalda alta')}
        onClick={click('espalda_alta')} readOnly={readOnly} />

      {/* ── Lower back ── */}
      <Zone id="espalda_baja" d="M40,90 L80,90 L78,110 L42,110 Z"
        fill={fill('espalda_baja')} label={label('espalda_baja', 'Espalda baja')}
        onClick={click('espalda_baja')} readOnly={readOnly} />

      {/* ── Left shoulder ── */}
      <Zone id="hombro_l" d="M22,46 L38,46 L36,62 L22,62 Z"
        fill={fill('hombro')} label={label('hombro', 'Hombro')}
        onClick={click('hombro')} readOnly={readOnly} />
      {/* ── Right shoulder ── */}
      <Zone id="hombro_r" d="M82,46 L98,46 L98,62 L84,62 Z"
        fill={fill('hombro')} label={label('hombro', 'Hombro')}
        onClick={click('hombro')} readOnly={readOnly} />

      {/* ── Left arm ── */}
      <Zone id="brazo_l" d="M14,62 L28,62 L26,100 L14,100 Z"
        fill={fill('brazo')} label={label('brazo', 'Brazo')}
        onClick={click('brazo')} readOnly={readOnly} />
      {/* ── Right arm ── */}
      <Zone id="brazo_r" d="M92,62 L106,62 L106,100 L94,100 Z"
        fill={fill('brazo')} label={label('brazo', 'Brazo')}
        onClick={click('brazo')} readOnly={readOnly} />

      {/* ── Left elbow ── */}
      <Zone id="codo_l" isCircle cx={19} cy={102} r={7}
        fill={fill('codo')} label={label('codo', 'Codo')}
        onClick={click('codo')} readOnly={readOnly} />
      {/* ── Right elbow ── */}
      <Zone id="codo_r" isCircle cx={101} cy={102} r={7}
        fill={fill('codo')} label={label('codo', 'Codo')}
        onClick={click('codo')} readOnly={readOnly} />

      {/* ── Left wrist ── */}
      <Zone id="muneca_l" d="M13,110 L26,110 L26,118 L13,118 Z"
        fill={fill('muneca')} label={label('muneca', 'Muñeca')}
        onClick={click('muneca')} readOnly={readOnly} />
      {/* ── Right wrist ── */}
      <Zone id="muneca_r" d="M94,110 L107,110 L107,118 L94,118 Z"
        fill={fill('muneca')} label={label('muneca', 'Muñeca')}
        onClick={click('muneca')} readOnly={readOnly} />

      {/* ── Left hand ── */}
      <Zone id="mano_l" d="M11,118 L27,118 L27,130 L11,130 Z"
        fill={fill('mano')} label={label('mano', 'Mano')}
        onClick={click('mano')} readOnly={readOnly} />
      {/* ── Right hand ── */}
      <Zone id="mano_r" d="M93,118 L109,118 L109,130 L93,130 Z"
        fill={fill('mano')} label={label('mano', 'Mano')}
        onClick={click('mano')} readOnly={readOnly} />

      {/* ── Hip ── */}
      <Zone id="cadera" d="M38,110 L82,110 L84,130 L36,130 Z"
        fill={fill('cadera')} label={label('cadera', 'Cadera')}
        onClick={click('cadera')} readOnly={readOnly} />

      {/* ── Left thigh ── */}
      <Zone id="muslo_l" d="M38,130 L58,130 L56,175 L38,175 Z"
        fill={fill('muslo')} label={label('muslo', 'Muslo')}
        onClick={click('muslo')} readOnly={readOnly} />
      {/* ── Right thigh ── */}
      <Zone id="muslo_r" d="M62,130 L82,130 L82,175 L64,175 Z"
        fill={fill('muslo')} label={label('muslo', 'Muslo')}
        onClick={click('muslo')} readOnly={readOnly} />

      {/* ── Left knee ── */}
      <Zone id="rodilla_l" isCircle cx={47} cy={178} r={8}
        fill={fill('rodilla')} label={label('rodilla', 'Rodilla')}
        onClick={click('rodilla')} readOnly={readOnly} />
      {/* ── Right knee ── */}
      <Zone id="rodilla_r" isCircle cx={73} cy={178} r={8}
        fill={fill('rodilla')} label={label('rodilla', 'Rodilla')}
        onClick={click('rodilla')} readOnly={readOnly} />

      {/* ── Left calf ── */}
      <Zone id="pantorrilla_l" d="M39,186 L55,186 L53,225 L39,225 Z"
        fill={fill('pantorrilla')} label={label('pantorrilla', 'Pantorrilla')}
        onClick={click('pantorrilla')} readOnly={readOnly} />
      {/* ── Right calf ── */}
      <Zone id="pantorrilla_r" d="M65,186 L81,186 L81,225 L67,225 Z"
        fill={fill('pantorrilla')} label={label('pantorrilla', 'Pantorrilla')}
        onClick={click('pantorrilla')} readOnly={readOnly} />

      {/* ── Left ankle ── */}
      <Zone id="tobillo_l" d="M37,226 L55,226 L55,238 L37,238 Z"
        fill={fill('tobillo')} label={label('tobillo', 'Tobillo')}
        onClick={click('tobillo')} readOnly={readOnly} />
      {/* ── Right ankle ── */}
      <Zone id="tobillo_r" d="M65,226 L83,226 L83,238 L65,238 Z"
        fill={fill('tobillo')} label={label('tobillo', 'Tobillo')}
        onClick={click('tobillo')} readOnly={readOnly} />

      {/* ── Left foot ── */}
      <Zone id="pie_l" d="M34,238 L56,238 L58,250 L30,250 Z"
        fill={fill('pie')} label={label('pie', 'Pie')}
        onClick={click('pie')} readOnly={readOnly} />
      {/* ── Right foot ── */}
      <Zone id="pie_r" d="M64,238 L86,238 L90,250 L62,250 Z"
        fill={fill('pie')} label={label('pie', 'Pie')}
        onClick={click('pie')} readOnly={readOnly} />
    </svg>
  );
}

export default BodyMap;
