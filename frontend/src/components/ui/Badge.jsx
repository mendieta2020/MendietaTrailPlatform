import React from 'react';
import { Chip } from '@mui/material';

const paletteByTone = {
  neutral: { bgcolor: '#F1F5F9', color: '#475569', borderColor: '#E2E8F0' },
  info: { bgcolor: '#EFF6FF', color: '#1D4ED8', borderColor: '#BFDBFE' },
  warning: { bgcolor: '#FFF7ED', color: '#C2410C', borderColor: '#FED7AA' },
  success: { bgcolor: '#ECFDF5', color: '#059669', borderColor: '#A7F3D0' },
  danger: { bgcolor: '#FEF2F2', color: '#B91C1C', borderColor: '#FECACA' },
};

export default function Badge({ label, tone = 'neutral', variant = 'soft', sx, ...props }) {
  const colors = paletteByTone[tone] || paletteByTone.neutral;
  const isOutlined = variant === 'outline';

  return (
    <Chip
      size="small"
      label={label}
      variant={isOutlined ? 'outlined' : 'filled'}
      sx={{
        ...(isOutlined
          ? { bgcolor: 'transparent', color: colors.color, borderColor: colors.borderColor }
          : { bgcolor: colors.bgcolor, color: colors.color }),
        fontWeight: 700,
        borderRadius: 1.25,
        ...sx,
      }}
      {...props}
    />
  );
}

