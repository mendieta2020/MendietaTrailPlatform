import React from 'react';
import { Card, CardContent, Avatar, Typography, Box, Chip } from '@mui/material';

function initials(firstName, lastName, username) {
  if (firstName || lastName) {
    return `${firstName?.[0] ?? ''}${lastName?.[0] ?? ''}`.toUpperCase() || '?';
  }
  return (username?.[0] ?? '?').toUpperCase();
}

export default function CoachCard({ coach }) {
  const { first_name, last_name, email, username, photo_url, specialties, years_experience } = coach;
  // Fallback chain: full name → username → email prefix
  const fullName =
    `${first_name ?? ''} ${last_name ?? ''}`.trim() ||
    username ||
    (email ? email.split('@')[0] : '');

  return (
    <Card
      sx={{
        borderRadius: 2,
        transition: 'box-shadow 0.2s',
        '&:hover': { boxShadow: 6 },
        border: '1px solid #e2e8f0',
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: specialties ? 1.5 : 0 }}>
          <Avatar
            src={photo_url || undefined}
            sx={{ bgcolor: '#3b82f6', fontWeight: 'bold', width: 44, height: 44 }}
          >
            {!photo_url && initials(first_name, last_name, username)}
          </Avatar>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={600} noWrap>
              {fullName || '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {email ?? ''}
            </Typography>
          </Box>
        </Box>
        {(specialties || years_experience > 0) && (
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 1 }}>
            {specialties && (
              <Chip label={specialties} size="small" sx={{ bgcolor: '#eff6ff', color: '#3b82f6', fontSize: '0.7rem', fontWeight: 600 }} />
            )}
            {years_experience > 0 && (
              <Chip label={`${years_experience} años exp.`} size="small" sx={{ bgcolor: '#f0fdf4', color: '#16a34a', fontSize: '0.7rem', fontWeight: 600 }} />
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
