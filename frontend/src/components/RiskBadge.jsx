import React from 'react';
import { Chip, Tooltip, Box, Typography } from '@mui/material';

const levelToColor = (level) => {
  if (level === 'HIGH') return { bg: '#FEF2F2', fg: '#B91C1C', border: '#FCA5A5', label: 'ALTO' };
  if (level === 'MEDIUM') return { bg: '#FFFBEB', fg: '#B45309', border: '#FCD34D', label: 'MEDIO' };
  return { bg: '#ECFDF5', fg: '#047857', border: '#6EE7B7', label: 'BAJO' };
};

const RiskBadge = ({ risk }) => {
  if (!risk || !risk.risk_level) {
    return <Chip label="—" size="small" variant="outlined" />;
  }

  const { bg, fg, border, label } = levelToColor(risk.risk_level);
  const reasons = Array.isArray(risk.risk_reasons) ? risk.risk_reasons : [];

  const tooltip = (
    <Box sx={{ p: 1 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 0.5 }}>
        Riesgo {label} • {risk.risk_score ?? 0}/100
      </Typography>
      {reasons.length === 0 ? (
        <Typography variant="body2">Sin razones disponibles.</Typography>
      ) : (
        reasons.map((r, idx) => (
          <Typography key={idx} variant="body2" sx={{ lineHeight: 1.3 }}>
            - {r}
          </Typography>
        ))
      )}
    </Box>
  );

  return (
    <Tooltip title={tooltip} placement="top" arrow>
      <Chip
        label={label}
        size="small"
        sx={{
          bgcolor: bg,
          color: fg,
          border: `1px solid ${border}`,
          fontWeight: 800,
          borderRadius: 1,
        }}
      />
    </Tooltip>
  );
};

export default RiskBadge;

