import React from 'react';
import { Card, CardContent, Avatar, Typography, Box } from '@mui/material';

function initials(firstName, lastName) {
  return `${firstName?.[0] ?? ''}${lastName?.[0] ?? ''}`.toUpperCase();
}

export default function AthleteCard({ athlete }) {
  const { first_name, last_name, email } = athlete;
  const fullName = `${first_name ?? ''} ${last_name ?? ''}`.trim();

  return (
    <Card
      sx={{
        borderRadius: 2,
        transition: 'box-shadow 0.2s',
        '&:hover': { boxShadow: 6 },
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar sx={{ bgcolor: '#F57C00', fontWeight: 'bold' }}>
            {initials(first_name, last_name)}
          </Avatar>
          <Box>
            <Typography variant="subtitle1" fontWeight={600}>
              {fullName || '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {email ?? '—'}
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
