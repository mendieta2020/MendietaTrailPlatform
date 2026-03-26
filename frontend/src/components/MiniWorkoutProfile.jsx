/**
 * MiniWorkoutProfile.jsx
 *
 * PR-145d: SVG mini-profile bar for a workout's block structure.
 *
 * Renders a horizontal proportional bar showing the distribution of
 * workout blocks by duration. All blocks use a neutral gray (#CBD5E1)
 * so the bar doesn't compete visually with the compliance color dot.
 *
 * Props:
 *   blocks: Array of WorkoutBlock objects with nested intervals
 *   estimatedDuration: fallback total duration (seconds) if blocks have no interval durations
 *
 * Rendering logic:
 *   1. If blocks have intervals with duration_seconds → proportional segments per block
 *   2. If blocks exist but no interval durations → equal-width segments (one per block)
 *   3. If estimatedDuration provided but no blocks → single full-width bar
 *   4. Otherwise → null (no render)
 */

export function MiniWorkoutProfile({ blocks, estimatedDuration }) {
  const blockList = blocks ?? [];

  if (blockList.length === 0 && !estimatedDuration) return null;

  // Try to compute per-block durations from intervals
  const blockDurations = blockList.map((block) =>
    (block.intervals ?? []).reduce((s, iv) => {
      return s + (iv.repetitions ?? 1) * (iv.duration_seconds ?? 0);
    }, 0)
  );

  const totalFromIntervals = blockDurations.reduce((s, d) => s + d, 0);

  let segments;

  if (totalFromIntervals > 0) {
    // Case 1: proper interval durations available
    segments = blockDurations.filter((d) => d > 0).map((d) => d / totalFromIntervals);
  } else if (blockList.length > 0) {
    // Case 2: blocks exist but no duration data — equal-width segments
    segments = blockList.map(() => 1 / blockList.length);
  } else if (estimatedDuration) {
    // Case 3: no blocks, but we know total duration — single bar
    segments = [1];
  } else {
    return null;
  }

  if (segments.length === 0) return null;

  // Build cumulative x offsets
  const bars = [];
  let x = 0;
  for (let i = 0; i < segments.length; i++) {
    const w = segments[i] * 100;
    bars.push({ x, w: Math.max(w - 0.8, 0.5) }); // 0.8% gap between blocks
    x += w;
  }

  return (
    <svg
      width="100%"
      height={16}
      style={{ display: 'block', borderRadius: 3, overflow: 'hidden', marginTop: 4 }}
      aria-hidden="true"
    >
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={`${bar.x}%`}
          y={2}
          width={`${bar.w}%`}
          height={12}
          fill="#CBD5E1"
          rx={2}
        />
      ))}
    </svg>
  );
}
