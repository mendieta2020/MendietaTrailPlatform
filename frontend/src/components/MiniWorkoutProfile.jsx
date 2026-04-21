/**
 * MiniWorkoutProfile.jsx
 *
 * PR-145d: SVG mini-profile bar for a workout's block structure.
 * PR-145g-fix5: Reverted fill to gray; robust blockReps helper;
 *   Case 2 uses block_type height (original logic) + repetition expansion.
 *
 * Zone height is derived from two sources (in priority order):
 *   1. interval.target_label — parsed for Z1–Z5, "tempo", "threshold", etc.
 *   2. block.block_type — fallback structural intensity (warmup/main/cooldown/etc.)
 *
 * Fill is always #CBD5E1 (gray) — color is intentionally kept neutral so
 * the profile is readable on small calendar cards and in the drawer alike.
 *
 * Props:
 *   blocks: Array of WorkoutBlock objects with nested intervals
 *   estimatedDuration: fallback total duration (seconds) if blocks have no interval durations
 */

const SVG_H = 32;

// Zone colors — matches WorkoutLibraryPage ZonePreviewBar palette
const ZONE_FILL = {
  Z1: '#3b82f6',
  Z2: '#22c55e',
  Z3: '#f59e0b',
  Z4: '#f97316',
  Z5: '#ef4444',
};
const ZONE_FILL_DEFAULT = '#CBD5E1';

function resolveZoneFill(targetLabel) {
  if (!targetLabel) return ZONE_FILL_DEFAULT;
  if (/\bz5\b|vo2|sprint/i.test(targetLabel))          return ZONE_FILL.Z5;
  if (/\bz4\b|threshold|umbral/i.test(targetLabel))     return ZONE_FILL.Z4;
  if (/\bz3\b|tempo/i.test(targetLabel))                return ZONE_FILL.Z3;
  if (/\bz2\b|aerobic|aer[oó]bico/i.test(targetLabel)) return ZONE_FILL.Z2;
  if (/\bz1\b|recovery|recuper/i.test(targetLabel))     return ZONE_FILL.Z1;
  return ZONE_FILL_DEFAULT;
}

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
  { re: /\bz5\b|vo2|sprint/i,           h: 0.95 },
  { re: /\bz4\b|threshold|umbral/i,      h: 0.75 },
  { re: /\bz3\b|tempo/i,                 h: 0.55 },
  { re: /\bz2\b|aerobic|aer[oó]bico/i,  h: 0.30 },
  { re: /\bz1\b|recovery|recuper/i,      h: 0.15 },
];

function resolveHeight(targetLabel, blockType) {
  if (targetLabel) {
    for (const { re, h } of LABEL_PATTERNS) {
      if (re.test(targetLabel)) return h * SVG_H;
    }
  }
  return (BLOCK_TYPE_HEIGHT[blockType] ?? 0.25) * SVG_H;
}

// Read repetitions safely: handles undefined, null, 0, or alternate field name.
function getBlockReps(block) {
  return Math.max(1, Number(block.repetitions || block.repeat_count || 1));
}

export function MiniWorkoutProfile({ blocks, estimatedDuration }) {
  const blockList = blocks ?? [];

  if (blockList.length === 0 && !estimatedDuration) return null;

  // Expand blocks into a flat list of {duration, distance, h} intervals,
  // respecting block repetitions for repeated blocks.
  // Both duration and distance are tracked so the right axis can be chosen.
  const intervals = [];
  for (const block of blockList) {
    const reps = getBlockReps(block);
    for (let r = 0; r < reps; r++) {
      for (const iv of (block.intervals ?? [])) {
        const ivReps = Math.max(1, Number(iv.repetitions) || 1);
        const dur  = ivReps * (iv.duration_seconds  ?? 0);
        const dist = ivReps * (iv.distance_meters   ?? 0);
        intervals.push({
          duration: dur,
          distance: dist,
          h: resolveHeight(iv.target_label, block.block_type),
          fill: resolveZoneFill(iv.target_label),
        });
      }
    }
  }

  const totalDistance = intervals.reduce((s, iv) => s + iv.distance, 0);
  const totalDuration = intervals.reduce((s, iv) => s + iv.duration, 0);

  let bars;

  if (totalDistance > 0) {
    // Case Distance (priority): distance-based intervals exist.
    // Use distance-proportional widths; skip time-only intervals (recovery,
    // rest) so they don't crowd out the main efforts.
    // Example: 1km warmup + 4×(1km Z4 + 180sec rest) + 1km cooldown
    //   → 6 distance bars (warmup, 4×Z4, cooldown); rest bars filtered out.
    bars = intervals
      .filter((iv) => iv.distance > 0)
      .map((iv, i) => ({
        key: i,
        wPct: (iv.distance / totalDistance) * 100,
        h: iv.h,
        fill: iv.fill,
      }));
  } else if (totalDuration > 0) {
    // Case Time: no distance data — proportional width from duration.
    bars = intervals
      .filter((iv) => iv.duration > 0)
      .map((iv, i) => ({
        key: i,
        wPct: (iv.duration / totalDuration) * 100,
        h: iv.h,
        fill: iv.fill,
      }));
  } else if (blockList.length > 0) {
    // Case Equal: no time or distance data — equal widths from block expansion.
    const expanded = [];
    for (const block of blockList) {
      const reps = getBlockReps(block);
      const h = (BLOCK_TYPE_HEIGHT[block.block_type] ?? 0.25) * SVG_H;
      for (let r = 0; r < reps; r++) expanded.push({ h, fill: ZONE_FILL_DEFAULT });
    }
    if (expanded.length === 0) return null;
    bars = expanded.map((b, i) => ({ key: i, wPct: 100 / expanded.length, h: b.h, fill: b.fill }));
  } else if (estimatedDuration) {
    // Case 3: no blocks, known total duration — single bar at default height
    bars = [{ key: 0, wPct: 100, h: 0.25 * SVG_H, fill: ZONE_FILL_DEFAULT }];
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
          fill={r.fill ?? ZONE_FILL_DEFAULT}
        />
      ))}
    </svg>
  );
}
