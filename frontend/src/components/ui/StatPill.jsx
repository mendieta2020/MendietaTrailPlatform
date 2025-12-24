import React from 'react';
import { Box, Typography } from '@mui/material';

export default function StatPill({ label, sx }) {
  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.75,
        px: 1,
        py: 0.5,
        borderRadius: 1.5,
        bgcolor: '#F8FAFC',
        border: '1px solid #E2E8F0',
        ...sx,
      }}
    >
      <Typography variant="caption" sx={{ color: '#475569', fontWeight: 700, lineHeight: 1 }}>
        {label}
      </Typography>
    </Box>
  );
}

