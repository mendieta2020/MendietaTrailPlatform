/**
 * MiniWorkoutProfile.jsx
 *
 * PR-145d: SVG mini-profile bar for a workout's block structure.
 *
 * Zone height is derived from two sources (in priority order):
 *   1. interval.target_label — parsed for Z1–Z5, "tempo", "threshold", etc.
 *   2. block.block_type — fallback structural intensity (warmup/main/cooldown/etc.)
 *
 * WorkoutInterval has no zone_type field. The available zone signals are:
 *   - target_label (free text: "Z2", "Threshold", "10k pace", etc.)
 *   - block_type on the parent block (warmup | main | cooldown | drill |
 *     strength | custom | recovery_step | free)
 *
 * Props:
 *   blocks: Array of WorkoutBlock objects with nested intervals
 *   estimatedDuration: fallback total duration (seconds) if blocks have no interval durations
 */

const SVG_H = 32;

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

export function MiniWorkoutProfile({ blocks, estimatedDuration }) {
  const blockList = blocks ?? [];

  if (blockList.length === 0 && !estimatedDuration) return null;

  // Expand blocks into a flat list of {duration, h} intervals,
  // respecting block.repetitions for repeated blocks.
  const intervals = [];
  for (const block of blockList) {
    const blockReps = block.repetitions ?? 1;
    for (let r = 0; r < blockReps; r++) {
      for (const iv of (block.intervals ?? [])) {
        const dur = (iv.repetitions ?? 1) * (iv.duration_seconds ?? 0);
        intervals.push({
          duration: dur,
          h: resolveHeight(iv.target_label, block.block_type),
        });
      }
    }
  }

  const totalDuration = intervals.reduce((s, iv) => s + iv.duration, 0);

  let bars;

  if (totalDuration > 0) {
    // Case 1: interval durations available → proportional width + zone height
    bars = intervals
      .filter((iv) => iv.duration > 0)
      .map((iv, i) => ({
        key: i,
        wPct: (iv.duration / totalDuration) * 100,
        h: iv.h,
      }));
  } else if (blockList.length > 0) {
    // Case 2: blocks exist but no duration — equal width, block_type height
    bars = blockList.map((block, i) => ({
      key: i,
      wPct: 100 / blockList.length,
      h: resolveHeight(null, block.block_type),
    }));
  } else if (estimatedDuration) {
    // Case 3: no blocks, known total duration — single bar at default height
    bars = [{ key: 0, wPct: 100, h: resolveHeight(null, null) }];
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
          fill="#CBD5E1"
        />
      ))}
    </svg>
  );
}
