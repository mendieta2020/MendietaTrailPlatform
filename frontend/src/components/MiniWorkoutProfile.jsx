/**
 * MiniWorkoutProfile.jsx
 *
 * PR-145d: SVG mini-profile bar for a workout's block structure.
 *
 * Renders a horizontal bar showing the intensity profile of the workout:
 * - Width of each bar: proportional to interval duration vs total
 * - Height of each bar: proportional to zone intensity (ZONE_HEIGHT map)
 * - Bars grow upward from the SVG bottom baseline
 * - All bars use neutral gray (#CBD5E1) so the bar doesn't compete
 *   visually with the compliance color dot.
 *
 * Props:
 *   blocks: Array of WorkoutBlock objects with nested intervals
 *   estimatedDuration: fallback total duration (seconds) if blocks have no interval durations
 *
 * Rendering logic:
 *   1. If blocks have intervals with duration_seconds → per-interval height + width bars
 *      (block repetitions expand sub-intervals N times)
 *   2. If blocks exist but no interval durations → equal-width, default-height segments
 *   3. If estimatedDuration provided but no blocks → single full-width bar at default height
 *   4. Otherwise → null (no render)
 */

const SVG_H = 32;

const ZONE_HEIGHT = {
  z1:       0.15,
  z2:       0.30,
  z3:       0.55,
  z4:       0.75,
  z5:       0.95,
  recovery: 0.10,
  warmup:   0.20,
  cooldown: 0.20,
  default:  0.25,
};

function zoneH(zone_type) {
  return (ZONE_HEIGHT[zone_type] ?? ZONE_HEIGHT.default) * SVG_H;
}

export function MiniWorkoutProfile({ blocks, estimatedDuration }) {
  const blockList = blocks ?? [];

  if (blockList.length === 0 && !estimatedDuration) return null;

  // Expand blocks into a flat list of {duration, zone_type} intervals,
  // respecting block.repetitions for repeated blocks.
  const intervals = [];
  for (const block of blockList) {
    const reps = block.repetitions ?? 1;
    for (let r = 0; r < reps; r++) {
      for (const iv of (block.intervals ?? [])) {
        intervals.push({
          duration: (iv.repetitions ?? 1) * (iv.duration_seconds ?? 0),
          zone_type: iv.zone_type ?? null,
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
        h: zoneH(iv.zone_type),
      }));
  } else if (blockList.length > 0) {
    // Case 2: blocks exist but no duration — equal width, default height
    bars = blockList.map((block, i) => ({
      key: i,
      wPct: 100 / blockList.length,
      h: zoneH(null),
    }));
  } else if (estimatedDuration) {
    // Case 3: no blocks, known total duration — single bar at default height
    bars = [{ key: 0, wPct: 100, h: zoneH(null) }];
  } else {
    return null;
  }

  if (bars.length === 0) return null;

  // Build cumulative x offsets (no gap between bars — contiguous profile)
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
