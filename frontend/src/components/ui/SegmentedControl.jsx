import React from 'react';
import { ToggleButton, ToggleButtonGroup } from '@mui/material';

export default function SegmentedControl({ value, onChange, options, size = 'small', sx }) {
  return (
    <ToggleButtonGroup
      exclusive
      value={value}
      onChange={(_, next) => {
        if (next === null || next === undefined) return;
        onChange?.(next);
      }}
      size={size}
      sx={{
        bgcolor: '#F1F5F9',
        p: 0.5,
        borderRadius: 2,
        '& .MuiToggleButton-root': {
          textTransform: 'none',
          fontWeight: 700,
          border: 0,
          borderRadius: 1.5,
          px: 1.5,
          color: '#475569',
        },
        '& .MuiToggleButton-root.Mui-selected': {
          bgcolor: 'white',
          color: '#0F172A',
          boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
        },
        '& .MuiToggleButton-root.Mui-selected:hover': {
          bgcolor: 'white',
        },
        ...sx,
      }}
    >
      {options.map((opt) => (
        <ToggleButton key={opt.value} value={opt.value} aria-label={opt.label}>
          {opt.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

