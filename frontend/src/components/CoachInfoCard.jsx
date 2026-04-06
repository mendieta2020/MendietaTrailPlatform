import React from 'react';
import { Box, Typography, Paper, Button, Tooltip } from '@mui/material';
import { MessageSquare } from 'lucide-react';

export default function CoachInfoCard({ coach, orgName }) {
  if (!coach) {
    return (
      <Paper
        sx={{
          mb: 2, borderRadius: 3, overflow: 'hidden',
          border: '1px solid', borderColor: 'divider',
          boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        }}
      >
        <Box sx={{ p: 2.5, display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{
            width: 48, height: 48, borderRadius: 2, bgcolor: '#e2e8f0',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <Typography sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '1.2rem' }}>?</Typography>
          </Box>
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#64748B' }}>
              Tu coach será asignado pronto
            </Typography>
            <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block' }}>
              {orgName
                ? `El equipo de ${orgName} está revisando tu perfil.`
                : 'El equipo está revisando tu perfil para asignarte el coach ideal.'}
            </Typography>
          </Box>
        </Box>
      </Paper>
    );
  }

  const initials = coach.name
    ? coach.name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
    : '?';

  return (
    <Paper
      sx={{
        mb: 2,
        borderRadius: 3,
        overflow: 'hidden',
        border: '1px solid',
        borderColor: 'divider',
        borderTop: '3px solid transparent',
        borderImage: 'linear-gradient(90deg, #00D4AA, #3b82f6) 1',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
      }}
    >
      <Box sx={{ p: 2.5, display: 'flex', alignItems: 'center', gap: 2 }}>
        {/* Avatar */}
        <Box
          sx={{
            width: 48, height: 48, borderRadius: 2,
            bgcolor: '#3b82f6', display: 'flex', alignItems: 'center',
            justifyContent: 'center', flexShrink: 0,
          }}
        >
          <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: '1rem' }}>
            {initials}
          </Typography>
        </Box>

        {/* Info */}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
            {coach.name}
          </Typography>
          <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>
            Head Coach{orgName ? ` · ${orgName}` : ''}
          </Typography>
          {(coach.specialties || coach.years_experience > 0) && (
            <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mt: 0.25 }}>
              {[
                coach.specialties,
                coach.years_experience > 0 ? `${coach.years_experience} años exp.` : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
          )}
        </Box>

        {/* Message button — disabled until PR-167 */}
        <Tooltip title="Próximamente" arrow>
          <span>
            <Button
              size="small"
              variant="outlined"
              startIcon={<MessageSquare size={14} />}
              disabled
              sx={{
                flexShrink: 0,
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.75rem',
              }}
            >
              Mensaje
            </Button>
          </span>
        </Tooltip>
      </Box>
    </Paper>
  );
}
