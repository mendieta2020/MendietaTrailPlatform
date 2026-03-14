import React from 'react';
import { Card, CardContent, Typography } from '@mui/material';

const MAX_DESC = 100;

export default function TeamCard({ team }) {
  const { name, description } = team;
  const truncated =
    description && description.length > MAX_DESC
      ? `${description.slice(0, MAX_DESC)}…`
      : description;

  return (
    <Card
      sx={{
        borderRadius: 2,
        transition: 'box-shadow 0.2s',
        '&:hover': { boxShadow: 6 },
      }}
    >
      <CardContent>
        <Typography variant="subtitle1" fontWeight={600}>
          {name ?? '—'}
        </Typography>
        {truncated && (
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            {truncated}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
