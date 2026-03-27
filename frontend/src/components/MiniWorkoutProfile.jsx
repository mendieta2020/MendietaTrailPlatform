/**
 * MiniWorkoutProfile.jsx
 *
 * PR-145d: SVG mini-profile bar for a workout's block structure.
 * PR-145g-fix4: Added zone-aware colors; robust repetitions fallback.
 *
 * Zone height and color are derived from two sources (in priority order):
 *   1. interval.target_label — parsed for Z1–Z5, "tempo", "threshold", etc.
 *   2. block.block_type — fallback structural intensity (warmup/main/cooldown/etc.)
 *
 * Props:
 *   blocks: Array of WorkoutBlock objects with nested intervals
 *   estimatedDuration: fallback total duration (seconds) if blocks have no interval durations
 */

const SVG_H = 32;

const ZONE_COLORS_MINI = {
  Z1: '#94A3B8',
  Z2: '#60A5FA',
  Z3: '#34D399',
  Z4: '#FBBF24',
  Z5: '#F87171',
};

// Block-type → height ratio (0–1). Main set gets highest default.
const BLOCK_TYPE_HEIGHT = {
  warmup:        0.20,
  cooldown:      0.20,
  recovery_step: 0.10,
  drill:         0.35,
  strength:      0.55,
  main:          0.70,
  custom:        0.30,
  free:          0.25,
};

// Patterns parsed from interval.target_label (case-insensitive)
const LABEL_PATTERNS = [
  { re: /\bz5\b|vo2|sprint/i,           h: 0.95, zone: 'Z5' },
  { re: /\bz4\b|threshold|umbral/i,      h: 0.75, zone: 'Z4' },
  { re: /\bz3\b|tempo/i,                 h: 0.55, zone: 'Z3' },
  { re: /\bz2\b|aerobic|aer[oó]bico/i,  h: 0.30, zone: 'Z2' },
  { re: /\bz1\b|recovery|recuper/i,      h: 0.15, zone: 'Z1' },
];

function resolveHeightAndZone(targetLabel, blockType) {
  if (targetLabel) {
    for (const { re, h, zone } of LABEL_PATTERNS) {
      if (re.test(targetLabel)) return { h: h * SVG_H, zone };
    }
  }
  return { h: (BLOCK_TYPE_HEIGHT[blockType] ?? 0.25) * SVG_H, zone: null };
}

// Safely read repetitions — handles undefined, null, 0, or alternate field names.
function blockReps(block) {
  return Math.max(1, Number(block.repetitions || block.repeat_count || 1));
}

export function MiniWorkoutProfile({ blocks, estimatedDuration }) {
  const blockList = blocks ?? [];

  if (blockList.length === 0 && !estimatedDuration) return null;

  // Expand blocks into a flat list of {duration, h, zone} intervals,
  // respecting block repetitions for repeated blocks.
  const intervals = [];
  for (const block of blockList) {
    const reps = blockReps(block);
    for (let r = 0; r < reps; r++) {
      for (const iv of (block.intervals ?? [])) {
        const dur = Math.max(1, Number(iv.repetitions) || 1) * (iv.duration_seconds ?? 0);
        const { h, zone } = resolveHeightAndZone(iv.target_label, block.block_type);
        intervals.push({ duration: dur, h, zone });
      }
    }
  }

  const totalDuration = intervals.reduce((s, iv) => s + iv.duration, 0);

  let bars;

  if (totalDuration > 0) {
    // Case 1: interval durations available → proportional width + zone height/color
    bars = intervals
      .filter((iv) => iv.duration > 0)
      .map((iv, i) => ({
        key: i,
        wPct: (iv.duration / totalDuration) * 100,
        h: iv.h,
        zone: iv.zone,
      }));
  } else if (blockList.length > 0) {
    // Case 2: blocks exist but no duration (distance-based) — equal width,
    // best zone height/color from intervals; expand repeated blocks.
    const expanded = [];
    for (const block of blockList) {
      const reps = blockReps(block);
      // Find the highest-intensity interval to represent this block's color + height.
      let best = resolveHeightAndZone(null, block.block_type);
      for (const iv of (block.intervals ?? [])) {
        const candidate = resolveHeightAndZone(iv.target_label, block.block_type);
        if (candidate.h > best.h) best = candidate;
      }
      for (let r = 0; r < reps; r++) expanded.push({ h: best.h, zone: best.zone });
    }
    if (expanded.length === 0) return null;
    bars = expanded.map((b, i) => ({ key: i, wPct: 100 / expanded.length, h: b.h, zone: b.zone }));
  } else if (estimatedDuration) {
    // Case 3: no blocks, known total duration — single bar at default height
    bars = [{ key: 0, wPct: 100, h: 0.25 * SVG_H, zone: null }];
  } else {
    return null;
  }

  if (bars.length === 0) return null;

  // Build cumulative x offsets (no gap — contiguous profile)
  const rects = bars.reduce((acc, bar) => {
    const prevX = acc.length > 0 ? acc[acc.length - 1].x + acc[acc.length - 1].wPct : 0;
    acc.push({ ...bar, x: prevX });
    return acc;
  }, []);

  return (
    <svg
      width="100%"
      height={SVG_H}
      style={{ display: 'block', overflow: 'visible', marginTop: 4 }}
      aria-hidden="true"
    >
      {rects.map((r) => (
        <rect
          key={r.key}
          x={`${r.x}%`}
          y={SVG_H - r.h}
          width={`${r.wPct}%`}
          height={r.h}
          fill={ZONE_COLORS_MINI[r.zone] ?? '#CBD5E1'}
        />
      ))}
    </svg>
  );
}
