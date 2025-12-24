import React from 'react';
import { Paper } from '@mui/material';

export default function Card({ children, sx, ...props }) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 3,
        borderRadius: 2,
        border: '1px solid #E2E8F0',
        boxShadow: '0 2px 10px rgba(0,0,0,0.03)',
        ...sx,
      }}
      {...props}
    >
      {children}
    </Paper>
  );
}

