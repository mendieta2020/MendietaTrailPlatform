import React from 'react';
import { Skeleton as MUISkeleton, Stack } from '@mui/material';

export function SkeletonLine({ width = '100%', height = 14, sx }) {
  return <MUISkeleton variant="text" width={width} height={height} sx={sx} />;
}

export function SkeletonBlock({ height = 64, sx }) {
  return <MUISkeleton variant="rounded" height={height} sx={{ borderRadius: 2, ...sx }} />;
}

export default function SkeletonList({ rows = 5 }) {
  return (
    <Stack spacing={1.25}>
      {Array.from({ length: rows }).map((_, idx) => (
        <Stack key={idx} spacing={0.5}>
          <SkeletonLine height={16} width="80%" />
          <SkeletonLine height={14} width="55%" />
        </Stack>
      ))}
    </Stack>
  );
}

