import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom'; // <--- IMPORTANTE: Para navegar entre pantallas
import { 
  Box, Typography, Button, Grid, Paper, Avatar, Chip, 
  IconButton, Dialog, DialogTitle, DialogContent, DialogActions, TextField, 
  AvatarGroup, CircularProgress, Tooltip
} from '@mui/material';
import { Add, Groups, MoreVert, CalendarMonth } from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';

const Teams = () => {
  const navigate = useNavigate(); // Hook de navegación
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openModal, setOpenModal] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDesc, setNewTeamDesc] = useState('');

  // 1. Cargar Equipos desde la API
  const fetchTeams = async () => {
    try {
      setLoading(true);
      const res = await client.get('/api/equipos/');
      const payload = res.data?.results ?? res.data ?? [];
      setTeams(Array.isArray(payload) ? payload : []);
    } catch (err) {
      console.error("Error cargando equipos:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeams();
  }, []);

  // 2. Crear Nuevo Equipo
  const handleCreateTeam = async () => {
    try {
      if (!newTeamName.trim()) return;
      
      const payload = {
        nombre: newTeamName,
        descripcion: newTeamDesc,
        color_identificador: '#F57C00' // Naranja Mendieta por defecto
      };

      await client.post('/api/equipos/', payload);
      
      // Limpieza y recarga
      setOpenModal(false);
      setNewTeamName('');
      setNewTeamDesc('');
      fetchTeams(); 
      
    } catch (err) {
      console.error(err);
      alert("Error: No se pudo crear el grupo. Verifica si el nombre ya existe.");
    }
  };

  // Función para ir al detalle
  const goToTeamDetail = (teamId) => {
    navigate(`/teams/${teamId}`);
  };

  const safeTeams = Array.isArray(teams) ? teams : [];

  return (
    <Layout>
      {/* HEADER */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Grupos de Entrenamiento</Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>Gestiona tus escuadrones y planifica en masa.</Typography>
        </Box>
        <Button 
            variant="contained" 
            startIcon={<Add />}
            onClick={() => setOpenModal(true)}
            sx={{ 
              bgcolor: '#F57C00', 
              borderRadius: 2, 
              textTransform: 'none', 
              fontWeight: 600,
              boxShadow: '0 4px 14px 0 rgba(245, 124, 0, 0.39)'
            }}
        >
            Nuevo Grupo
        </Button>
      </Box>

      {/* LISTA DE EQUIPOS (GRID) */}
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box>
      ) : safeTeams.length === 0 ? (
        <Paper sx={{ p: 6, textAlign: 'center', borderRadius: 4, border: '2px dashed #CBD5E1', bgcolor: '#F8FAFC' }}>
          <Groups sx={{ fontSize: 60, color: '#94A3B8', mb: 2 }} />
          <Typography variant="h6" color="textSecondary" sx={{ fontWeight: 600 }}>No tienes grupos creados</Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 3, maxWidth: 400, mx: 'auto' }}>
            Crea tu primer grupo (ej: "Inicial Montaña") para asignar planes a múltiples atletas a la vez.
          </Typography>
          <Button variant="outlined" onClick={() => setOpenModal(true)} sx={{ borderRadius: 2, textTransform: 'none' }}>
            Crear mi primer grupo
          </Button>
        </Paper>
      ) : (
        <Grid container spacing={3}>
          {safeTeams.map((team) => (
            <Grid item xs={12} sm={6} md={4} key={team.id}>
              <Paper 
                onClick={() => goToTeamDetail(team.id)} // Toda la tarjeta es clickable
                sx={{ 
                  p: 3, 
                  borderRadius: 3, 
                  position: 'relative', 
                  transition: 'all 0.3s ease',
                  cursor: 'pointer',
                  border: '1px solid transparent',
                  '&:hover': { 
                    transform: 'translateY(-4px)', 
                    boxShadow: '0 12px 24px rgba(0,0,0,0.08)',
                    borderColor: '#F57C00' // Borde naranja al pasar el mouse
                  } 
                }}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                  <Chip 
                    label={`${team.cantidad_alumnos} Atletas`} 
                    size="small" 
                    sx={{ bgcolor: '#FFF7ED', color: '#C2410C', fontWeight: 700, borderRadius: 1.5 }} 
                  />
                  <IconButton 
                    size="small" 
                    onClick={(e) => { e.stopPropagation(); /* Aquí iría menú de opciones */ }}
                  >
                    <MoreVert />
                  </IconButton>
                </Box>
                
                <Typography variant="h6" sx={{ fontWeight: 800, mb: 1, color: '#1E293B' }}>
                  {team.nombre}
                </Typography>
                
                <Typography variant="body2" color="textSecondary" sx={{ mb: 3, height: 40, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                  {team.descripcion || "Sin descripción disponible para este grupo."}
                </Typography>

                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 'auto', pt: 2, borderTop: '1px solid #F1F5F9' }}>
                  {/* Avatares (Placeholder visual hasta tener alumnos reales con foto) */}
                  <Tooltip title="Miembros del equipo">
                    <AvatarGroup max={4} sx={{ '& .MuiAvatar-root': { width: 28, height: 28, fontSize: 12 } }}>
                      <Avatar sx={{ bgcolor: '#3B82F6' }}>A</Avatar>
                      <Avatar sx={{ bgcolor: '#EF4444' }}>B</Avatar>
                      <Avatar sx={{ bgcolor: '#10B981' }}>C</Avatar>
                    </AvatarGroup>
                  </Tooltip>
                  
                  <Button 
                    size="small" 
                    variant="text" 
                    endIcon={<CalendarMonth fontSize="small" />}
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      goToTeamDetail(team.id); 
                    }}
                    sx={{ fontWeight: 700, textTransform: 'none', color: '#F57C00' }}
                  >
                    Ver Calendario
                  </Button>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {/* MODAL CREAR EQUIPO */}
      <Dialog open={openModal} onClose={() => setOpenModal(false)} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 800, pb: 1 }}>Nuevo Grupo</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            Crea un espacio para agrupar atletas por nivel o disciplina.
          </Typography>
          <TextField
            autoFocus
            margin="dense"
            label="Nombre del Grupo"
            placeholder="Ej: Avanzados 42K"
            fullWidth
            variant="outlined"
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Descripción (Opcional)"
            placeholder="Objetivo principal del grupo..."
            fullWidth
            multiline
            rows={3}
            variant="outlined"
            value={newTeamDesc}
            onChange={(e) => setNewTeamDesc(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ p: 3, pt: 0 }}>
          <Button onClick={() => setOpenModal(false)} color="inherit" sx={{ borderRadius: 2, textTransform: 'none' }}>
            Cancelar
          </Button>
          <Button 
            onClick={handleCreateTeam} 
            variant="contained" 
            disableElevation
            sx={{ bgcolor: '#F57C00', color: 'white', borderRadius: 2, textTransform: 'none', fontWeight: 600, '&:hover': { bgcolor: '#ea580c' } }}
          >
            Crear Grupo
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default Teams;
