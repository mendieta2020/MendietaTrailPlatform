import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Box, Typography, Paper, Tabs, Tab, Button, Avatar, 
  List, ListItem, ListItemAvatar, ListItemText, IconButton, Divider,
  Chip
} from '@mui/material';
import { 
  ArrowBack, PersonAdd, CalendarMonth, Group, Delete 
} from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';
import AddMemberModal from '../components/AddMemberModal'; 
import TemplateLibrary from '../components/TemplateLibrary'; 

// Componente TabPanel (Lógica para cambiar pestañas)
function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const TeamDetail = () => {
  const { id } = useParams(); // ID del grupo
  const navigate = useNavigate();
  const [team, setTeam] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [athletes, setAthletes] = useState([]); 
  
  // Estado para controlar el Modal de Agregar Atletas
  const [openAddModal, setOpenAddModal] = useState(false);

  // Función para cargar los datos
  const fetchTeamData = async () => {
    try {
      const resTeam = await client.get(`/api/equipos/${id}/`);
      setTeam(resTeam.data);

      const resAthletes = await client.get(`/api/equipos/${id}/alumnos/`);
      setAthletes(resAthletes.data);
    } catch (err) {
      console.error("Error cargando equipo:", err);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTeamData();
  }, [id]);

  const handleMembersAdded = () => {
    fetchTeamData(); 
  };

  // --- LÓGICA DE DROP & ASSIGN ---
  const handleDrop = async (e) => {
    e.preventDefault();
    const templateId = e.dataTransfer.getData("templateId");
    const templateTitle = e.dataTransfer.getData("templateTitle");

    if (!templateId) return;

    const fechaInicio = new Date().toISOString().split('T')[0]; 

    const confirmacion = window.confirm(
        `¿Estás seguro de asignar la plantilla "${templateTitle}" a los ${athletes.length} miembros del grupo?\n\nFecha de inicio: ${fechaInicio}`
    );

    if (!confirmacion) return;

    try {
        const res = await client.post(`/api/plantillas/${templateId}/aplicar_a_equipo/`, {
            equipo_id: id,
            fecha_inicio: fechaInicio
        });

        alert(`✅ ¡Planificación Exitosa!\n\nSe han creado ${res.data.alumnos_afectados} entrenamientos en los calendarios individuales.`);

    } catch (err) {
        console.error("Error asignando plantilla:", err);
        const errorMsg = err.response?.data?.error || "Error de conexión";
        alert(`❌ Ocurrió un error: ${errorMsg}`);
    }
  };

  if (!team) return <Layout><Typography>Cargando...</Typography></Layout>;

  return (
    <Layout>
      {/* HEADER */}
      <Box sx={{ mb: 4, display: 'flex', alignItems: 'center' }}>
        <IconButton onClick={() => navigate('/teams')} sx={{ mr: 2 }}>
          <ArrowBack />
        </IconButton>
        <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: '#0F172A' }}>
                {team.nombre}
            </Typography>
            <Typography variant="body2" color="textSecondary">
                Gestión de Grupo • {athletes.length} Miembros
            </Typography>
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        <Button 
            variant="outlined" 
            color="error" 
            startIcon={<Delete />}
            sx={{ mr: 2 }}
        >
            Eliminar Grupo
        </Button>
        <Button 
            variant="contained" 
            sx={{ bgcolor: '#F57C00' }}
            startIcon={<PersonAdd />}
            onClick={() => setOpenAddModal(true)} 
        >
            Agregar Atleta
        </Button>
      </Box>

      {/* PESTAÑAS */}
      <Paper sx={{ width: '100%', borderRadius: 2 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs 
            value={tabValue} 
            onChange={(e, val) => setTabValue(val)} 
            textColor="primary"
            indicatorColor="primary"
            sx={{ '& .MuiTab-root': { textTransform: 'none', fontWeight: 600 } }}
          >
            <Tab icon={<Group fontSize="small" />} iconPosition="start" label="Miembros" />
            <Tab icon={<CalendarMonth fontSize="small" />} iconPosition="start" label="Calendario Grupal" />
          </Tabs>
        </Box>

        {/* PESTAÑA 1: LISTA DE MIEMBROS (AHORA SÍ ES CLICKEABLE) */}
        <TabPanel value={tabValue} index={0}>
            {athletes.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
                    <Typography>Este grupo aún no tiene atletas.</Typography>
                    <Typography variant="caption">Usa el botón "Agregar Atleta" arriba a la derecha.</Typography>
                </Box>
            ) : (
                <List>
                    {athletes.map((athlete) => (
                        <React.Fragment key={athlete.id}>
                            <ListItem 
                                button // <--- Habilita el comportamiento de botón
                                onClick={() => navigate(`/athletes/${athlete.id}`)} // <--- Navega al perfil
                                sx={{ 
                                    cursor: 'pointer',
                                    transition: '0.2s',
                                    '&:hover': { bgcolor: '#f1f5f9' } // Efecto visual al pasar el mouse
                                }}
                            >
                                <ListItemAvatar>
                                    <Avatar sx={{ bgcolor: '#1976d2' }}>
                                        {athlete.nombre ? athlete.nombre.charAt(0) : '?'}
                                    </Avatar>
                                </ListItemAvatar>
                                <ListItemText 
                                    primary={`${athlete.nombre} ${athlete.apellido}`} 
                                    secondary={athlete.email} 
                                />
                                <Chip label="Activo" color="success" size="small" variant="outlined" />
                            </ListItem>
                            <Divider component="li" />
                        </React.Fragment>
                    ))}
                </List>
            )}
        </TabPanel>

        {/* PESTAÑA 2: CALENDARIO DE EQUIPO */}
        <TabPanel value={tabValue} index={1} sx={{ p: 0 }}>
            <Box sx={{ display: 'flex', height: '70vh', borderRadius: 2, overflow: 'hidden' }}>
                <Box sx={{ width: '280px', minWidth: '280px', bgcolor: 'white', borderRight: '1px solid #e0e0e0' }}>
                    <TemplateLibrary />
                </Box>
                <Box sx={{ flexGrow: 1, bgcolor: '#f8fafc', p: 3 }}>
                    <Box 
                        sx={{ 
                            height: '100%', 
                            border: '2px dashed #cbd5e1', 
                            borderRadius: 2, 
                            display: 'flex', 
                            flexDirection: 'column',
                            alignItems: 'center', 
                            justifyContent: 'center',
                            bgcolor: 'white',
                            transition: 'all 0.3s ease',
                            '&:hover': { borderColor: '#F57C00', bgcolor: '#fff7ed' }
                        }}
                        onDragOver={(e) => e.preventDefault()} 
                        onDrop={handleDrop} 
                    >
                        <CalendarMonth sx={{ fontSize: 60, color: '#94a3b8', mb: 2 }} />
                        <Typography variant="h6" color="textSecondary" sx={{ fontWeight: 600 }}>
                            Arrastra sesiones aquí
                        </Typography>
                        <Typography variant="body2" color="textSecondary" sx={{ maxWidth: 300, textAlign: 'center' }}>
                            Selecciona una plantilla de la izquierda y suéltala en este espacio para planificar masivamente.
                        </Typography>
                    </Box>
                </Box>
            </Box>
        </TabPanel>
      </Paper>

      {/* MODAL */}
      <AddMemberModal 
        open={openAddModal} 
        onClose={() => setOpenAddModal(false)}
        teamId={id}
        onMembersAdded={handleMembersAdded}
      />
    </Layout>
  );
};

export default TeamDetail;