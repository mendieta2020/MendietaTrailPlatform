import React from 'react';
import { Box, Typography, Paper, Button } from '@mui/material';
import { MessageSquare } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function CoachInfoCard({ coach, orgName }) {
  const navigate = useNavigate();
  if (!coach) return null;

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

        {/* Message button */}
        <Button
          size="small"
          variant="outlined"
          startIcon={<MessageSquare size={14} />}
          onClick={() => navigate('/athlete/messages')}
          sx={{
            flexShrink: 0,
            color: '#00D4AA',
            borderColor: '#00D4AA',
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '0.75rem',
            '&:hover': { borderColor: '#00BF99', bgcolor: 'rgba(0,212,170,0.04)' },
          }}
        >
          Mensaje
        </Button>
      </Box>
    </Paper>
  );
}
