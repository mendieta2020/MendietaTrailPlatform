import React, { useState, useEffect } from 'react';
import { 
  Box, Typography, Paper, List, ListItem, ListItemText, 
  Chip, TextField, InputAdornment, IconButton, CircularProgress, Divider
} from '@mui/material';
import { Search, FitnessCenter, DirectionsRun, PedalBike, Add } from '@mui/icons-material';
import client from '../api/client';

const TemplateLibrary = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const res = await client.get('/api/plantillas/');
      setTemplates(res.data);
    } catch (err) {
      console.error("Error cargando librería:", err);
    } finally {
      setLoading(false);
    }
  };

  // Icono dinámico según deporte
  const getIcon = (deporte) => {
    switch(deporte) {
      case 'RUN': case 'TRAIL': return <DirectionsRun fontSize="small" />;
      case 'CYCLING': case 'MTB': return <PedalBike fontSize="small" />;
      default: return <FitnessCenter fontSize="small" />;
    }
  };

  // Color dinámico según dificultad
  const getColor = (dificultad) => {
    switch(dificultad) {
      case 'HARD': return '#ef5350'; // Rojo
      case 'MODERATE': return '#ff9800'; // Naranja
      default: return '#4caf50'; // Verde
    }
  };

  const filteredList = templates.filter(t => 
    t.titulo.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column', borderRight: '1px solid #e0e0e0' }}>
      {/* HEADER */}
      <Box sx={{ p: 2, bgcolor: '#f8fafc', borderBottom: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#475569' }}>
            LIBRERÍA 📚
          </Typography>
          <IconButton size="small" sx={{ bgcolor: '#e2e8f0' }}>
            <Add fontSize="small" />
          </IconButton>
        </Box>
        <TextField
          fullWidth
          size="small"
          placeholder="Buscar sesión..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          InputProps={{
            startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
            sx: { fontSize: '0.85rem', bgcolor: 'white' }
          }}
        />
      </Box>

      {/* LISTA SCROLLABLE */}
      <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
        {loading ? (
          <Box sx={{ p: 3, textAlign: 'center' }}><CircularProgress size={20} /></Box>
        ) : filteredList.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="caption" color="textSecondary">No hay plantillas.</Typography>
          </Box>
        ) : (
          <List dense>
            {filteredList.map((tpl) => (
              <React.Fragment key={tpl.id}>
                <ListItem 
                  button 
                  sx={{ 
                    '&:hover': { bgcolor: '#f1f5f9' },
                    cursor: 'grab' // Cursor de manito para indicar arrastre
                  }}
                  draggable // ¡Habilita el arrastre nativo!
                  onDragStart={(e) => {
                    e.dataTransfer.setData("templateId", tpl.id);
                    e.dataTransfer.setData("templateTitle", tpl.titulo);
                  }}
                >
                  <Box sx={{ mr: 1.5, color: '#64748B', display: 'flex' }}>
                    {getIcon(tpl.deporte)}
                  </Box>
                  <ListItemText 
                    primary={
                      <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                        {tpl.titulo}
                      </Typography>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
                        <Chip 
                          label={tpl.dificultad_display || 'Normal'} 
                          size="small" 
                          sx={{ 
                            height: 16, 
                            fontSize: '0.65rem', 
                            bgcolor: getColor(tpl.etiqueta_dificultad), 
                            color: 'white' 
                          }} 
                        />
                         <Typography variant="caption" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                           • {tpl.deporte}
                         </Typography>
                      </Box>
                    }
                  />
                </ListItem>
                <Divider component="li" />
              </React.Fragment>
            ))}
          </List>
        )}
      </Box>
    </Paper>
  );
};

export default TemplateLibrary;