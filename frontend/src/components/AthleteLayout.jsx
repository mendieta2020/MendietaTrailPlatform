import React from 'react';
import { AppBar, Box, Container, Toolbar, Typography } from '@mui/material';

const AthleteLayout = ({ children }) => {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: '#F1F5F9' }}>
      <AppBar position="static" sx={{ bgcolor: '#0F172A' }}>
        <Toolbar>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Portal del Alumno
          </Typography>
        </Toolbar>
      </AppBar>
      <Container sx={{ py: 4 }} maxWidth="md">
        {children}
      </Container>
    </Box>
  );
};

export default AthleteLayout;
