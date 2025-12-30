import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom'; // <--- IMPORTANTE: Faltaba esto
import { 
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, 
  TableHead, TableRow, Avatar, Chip, IconButton, Button, TextField, InputAdornment 
} from '@mui/material';
import { Search, Edit, Add, NavigateNext } from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';
import RiskBadge from '../components/RiskBadge';
import { unpackResults } from '../api/pagination';

const Athletes = () => {
  const navigate = useNavigate(); // <--- Hook de navegación
  const [athletes, setAthletes] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchAthletes = async () => {
      try {
        const res = await client.get('/api/alumnos/?include_injury_risk=1');
        setAthletes(unpackResults(res.data));
      } catch (err) {
        console.error(err);
      }
    };
    fetchAthletes();
  }, []);

  // Filtro de búsqueda en tiempo real
  const filteredAthletes = athletes.filter(athlete => 
    athlete.nombre.toLowerCase().includes(searchTerm.toLowerCase()) || 
    athlete.apellido.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Layout>
      {/* Header de la Página */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Mis Alumnos</Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>Gestión integral de atletas.</Typography>
        </Box>
        <Button 
            variant="contained" 
            startIcon={<Add />}
            sx={{ bgcolor: '#F57C00', borderRadius: 2, textTransform: 'none', fontWeight: 600 }}
        >
            Nuevo Alumno
        </Button>
      </Box>

      {/* Barra de Búsqueda */}
      <Paper sx={{ p: 2, mb: 3, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
        <TextField 
            fullWidth 
            placeholder="Buscar por nombre..." 
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
                startAdornment: (
                    <InputAdornment position="start">
                        <Search sx={{ color: '#94A3B8' }} />
                    </InputAdornment>
                ),
            }}
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
        />
      </Paper>

      {/* Tabla de Alumnos */}
      <TableContainer component={Paper} sx={{ borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
        <Table>
          <TableHead sx={{ bgcolor: '#F8FAFC' }}>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ATLETA</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>ESTADO</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>PLAN</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>FITNESS</TableCell>
              <TableCell sx={{ fontWeight: 600, color: '#475569' }}>RIESGO</TableCell>
              <TableCell align="right" sx={{ fontWeight: 600, color: '#475569' }}>ACCIONES</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredAthletes.map((athlete) => (
              <TableRow 
                key={athlete.id} 
                hover
                onClick={() => navigate(`/athletes/${athlete.id}`)} // <--- AQUÍ ESTÁ LA MAGIA DEL CLIC
                sx={{ cursor: 'pointer' }} // <--- Cambia el cursor a manita
              >
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Avatar sx={{ bgcolor: '#0EA5E9', mr: 2, width: 32, height: 32, fontSize: '0.875rem' }}>
                      {athlete.nombre ? athlete.nombre.charAt(0) : '?'}
                      {athlete.apellido ? athlete.apellido.charAt(0) : ''}
                    </Avatar>
                    <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{athlete.nombre} {athlete.apellido}</Typography>
                        <Typography variant="caption" sx={{ color: '#94A3B8' }}>{athlete.email}</Typography>
                    </Box>
                  </Box>
                </TableCell>
                <TableCell>
                    <Chip 
                        label={(athlete.estado_actual || 'ACTIVO') === 'ACTIVO' ? "Activo" : "Inactivo"} 
                        size="small" 
                        sx={{ 
                            bgcolor: (athlete.estado_actual || 'ACTIVO') === 'ACTIVO' ? '#ECFDF5' : '#F1F5F9', 
                            color: (athlete.estado_actual || 'ACTIVO') === 'ACTIVO' ? '#059669' : '#64748B',
                            fontWeight: 600,
                            borderRadius: 1
                        }} 
                    />
                </TableCell>
                <TableCell>
                    <Typography variant="body2" sx={{ color: '#475569' }}>
                        Trail Elite
                    </Typography>
                </TableCell>
                <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
                        {/* Dato simulado hasta tener real */}
                        {(((athlete.id || 1) * 7) % 50) + 40} CTL
                    </Typography>
                </TableCell>
                <TableCell>
                  <RiskBadge risk={athlete.injury_risk} />
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={(e) => { e.stopPropagation(); /* Evita navegar al editar */ }}>
                    <Edit fontSize="small" />
                  </IconButton>
                  <IconButton size="small">
                    <NavigateNext />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Layout>
  );
};

export default Athletes;