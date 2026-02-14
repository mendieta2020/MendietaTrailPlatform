import React, { useState, useEffect } from 'react';
import { 
  Box, Typography, Paper, List, ListItem, ListItemText, 
  Chip, TextField, InputAdornment, IconButton, CircularProgress, Divider,
  Dialog, DialogTitle, DialogContent, DialogActions, Button, FormControl,
  InputLabel, Select, MenuItem, Alert
} from '@mui/material';
import { Search, FitnessCenter, DirectionsRun, PedalBike, Add } from '@mui/icons-material';
import client from '../api/client';

const TemplateLibrary = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createState, setCreateState] = useState({
    titulo: '',
    deporte: 'RUN',
    estructura: '{\n  "bloques": []\n}',
    descripcion_global: '',
  });
  const [createError, setCreateError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

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

  const formatLastUpdate = (tpl) => {
    const rawDate = tpl.ultima_actualizacion || tpl.created_at;
    if (!rawDate) return 'Sin fecha';
    const parsed = new Date(rawDate);
    if (Number.isNaN(parsed.getTime())) return 'Sin fecha';
    return parsed.toLocaleDateString();
  };

  const handleCreateChange = (field) => (event) => {
    setCreateState((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleOpenCreate = () => {
    setCreateError('');
    setIsCreateOpen(true);
  };

  const handleCloseCreate = () => {
    if (!isSaving) {
      setIsCreateOpen(false);
    }
  };

  const handleCreateTemplate = async () => {
    setCreateError('');
    let estructuraPayload = {};
    if (createState.estructura?.trim()) {
      try {
        estructuraPayload = JSON.parse(createState.estructura);
      } catch {
        setCreateError('La estructura debe ser un JSON válido.');
        return;
      }
    }

    try {
      setIsSaving(true);
      await client.post('/api/plantillas/', {
        titulo: createState.titulo,
        deporte: createState.deporte,
        estructura: estructuraPayload,
        descripcion_global: createState.descripcion_global,
      });
      setIsCreateOpen(false);
      setCreateState({
        titulo: '',
        deporte: 'RUN',
        estructura: '{\n  "bloques": []\n}',
        descripcion_global: '',
      });
      await fetchTemplates();
    } catch (error) {
      console.error('Error creando plantilla:', error);
      setCreateError('No se pudo crear la plantilla. Revisa los campos.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column', borderRight: '1px solid #e0e0e0' }}>
      {/* HEADER */}
      <Box sx={{ p: 2, bgcolor: '#f8fafc', borderBottom: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#475569' }}>
            LIBRERÍA 📚
          </Typography>
          <IconButton size="small" sx={{ bgcolor: '#e2e8f0' }} onClick={handleOpenCreate}>
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
                      <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
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
                         {tpl.version_actual ? (
                           <Typography variant="caption" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                             • v{tpl.version_actual}
                           </Typography>
                         ) : null}
                         <Typography variant="caption" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                           • Últ. act: {formatLastUpdate(tpl)}
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

      <Dialog open={isCreateOpen} onClose={handleCloseCreate} fullWidth maxWidth="sm">
        <DialogTitle>Nueva plantilla</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          {createError ? <Alert severity="error">{createError}</Alert> : null}
          <TextField
            label="Título"
            value={createState.titulo}
            onChange={handleCreateChange('titulo')}
            fullWidth
            required
          />
          <FormControl fullWidth>
            <InputLabel id="template-sport-label">Deporte</InputLabel>
            <Select
              labelId="template-sport-label"
              label="Deporte"
              value={createState.deporte}
              onChange={handleCreateChange('deporte')}
            >
              <MenuItem value="RUN">Running</MenuItem>
              <MenuItem value="TRAIL">Trail</MenuItem>
              <MenuItem value="CYCLING">Ciclismo</MenuItem>
              <MenuItem value="MTB">MTB</MenuItem>
              <MenuItem value="GYM">Gimnasio</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Descripción global"
            value={createState.descripcion_global}
            onChange={handleCreateChange('descripcion_global')}
            fullWidth
            multiline
            rows={2}
          />
          <TextField
            label="Estructura (JSON)"
            value={createState.estructura}
            onChange={handleCreateChange('estructura')}
            fullWidth
            multiline
            rows={6}
            helperText="Define bloques y pasos en formato JSON."
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleCloseCreate} disabled={isSaving}>
            Cancelar
          </Button>
          <Button
            variant="contained"
            onClick={handleCreateTemplate}
            disabled={isSaving || !createState.titulo.trim()}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default TemplateLibrary;
