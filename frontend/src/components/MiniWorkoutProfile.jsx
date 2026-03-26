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
 *
 * Returns null if there are no blocks or no intervals with duration data.
 */

function getTotalDuration(blocks) {
  let total = 0;
  for (const block of blocks) {
    for (const interval of block.intervals ?? []) {
      const reps = interval.repetitions ?? 1;
      const dur = interval.duration_seconds ?? 0;
      total += reps * dur;
    }
  }
  return total;
}

export function MiniWorkoutProfile({ blocks }) {
  if (!blocks?.length) return null;

  const total = getTotalDuration(blocks);
  if (total === 0) return null;

  // Build segments: one per block
  const segments = blocks.map((block) => {
    const blockDur = (block.intervals ?? []).reduce((s, iv) => {
      return s + (iv.repetitions ?? 1) * (iv.duration_seconds ?? 0);
    }, 0);
    return blockDur;
  }).filter((d) => d > 0);

  if (segments.length === 0) return null;

  return (
    <svg
      width="100%"
      height="8"
      style={{ display: 'block', borderRadius: 3, overflow: 'hidden', marginTop: 4 }}
      aria-hidden="true"
    >
      {segments.reduce((acc, dur, i) => {
        const pct = (dur / total) * 100;
        const x = acc.x;
        acc.rects.push(
          <rect
            key={i}
            x={`${x}%`}
            y={0}
            width={`${pct - 0.5}%`}
            height="8"
            fill="#CBD5E1"
            rx={1}
          />
        );
        acc.x += pct;
        return acc;
      }, { x: 0, rects: [] }).rects}
    </svg>
  );
}
