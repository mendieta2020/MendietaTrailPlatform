import React, { useState, useEffect, useCallback } from 'react';
import { 
  Dialog, DialogTitle, DialogContent, DialogActions, 
  Button, List, ListItem, ListItemText, ListItemAvatar, 
  Avatar, Checkbox, TextField, InputAdornment, Typography, Box, Chip 
} from '@mui/material';
import { Search, PersonAdd } from '@mui/icons-material';
import client from '../api/client';

const AddMemberModal = ({ open, onClose, teamId, onMembersAdded }) => {
  const [athletes, setAthletes] = useState([]); // Todos los alumnos
  const [selected, setSelected] = useState([]); // IDs seleccionados
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);

  // 1. Cargar alumnos al abrir el modal
  const fetchAvailableAthletes = useCallback(async () => {
    try {
      // Traemos TODOS los alumnos
      const res = await client.get('/api/alumnos/');
      // Filtramos: Solo mostramos los que NO están ya en este equipo
      // (Asumiendo que res.data trae el objeto completo, verificamos su equipo actual)
      const available = res.data.filter(a => a.equipo !== parseInt(teamId));
      setAthletes(available);
    } catch (err) {
      console.error("Error cargando atletas:", err);
    }
  }, [teamId]);

  useEffect(() => {
    if (open) {
      fetchAvailableAthletes();
      setSelected([]); // Resetear selección
      setSearchTerm('');
    }
  }, [open, fetchAvailableAthletes]);

  // 2. Manejar Selección (Checkbox)
  const handleToggle = (value) => () => {
    const currentIndex = selected.indexOf(value);
    const newChecked = [...selected];

    if (currentIndex === -1) {
      newChecked.push(value); // Agregar
    } else {
      newChecked.splice(currentIndex, 1); // Quitar
    }
    setSelected(newChecked);
  };

  // 3. Guardar Cambios (Bulk Update)
  const handleSave = async () => {
    try {
      setLoading(true);
      // Truco Profesional: Usamos Promise.all para enviar múltiples peticiones en paralelo
      // Esto es mucho más rápido que un bucle for normal.
      const promises = selected.map(athleteId => 
        client.patch(`/api/alumnos/${athleteId}/`, { equipo: teamId })
      );

      await Promise.all(promises);
      
      // Éxito
      onMembersAdded(); // Avisamos al padre que recargue
      onClose();
    } catch (err) {
      console.error("Error asignando atletas:", err);
      alert("Hubo un error al asignar los atletas.");
    } finally {
      setLoading(false);
    }
  };

  // Filtro de búsqueda visual
  const filteredAthletes = athletes.filter(a => 
    `${a.nombre} ${a.apellido}`.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 'bold' }}>
        Agregar Atletas al Grupo
      </DialogTitle>
      
      <DialogContent dividers>
        {/* Buscador */}
        <TextField
          fullWidth
          size="small"
          placeholder="Buscar por nombre..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: <InputAdornment position="start"><Search /></InputAdornment>,
          }}
          sx={{ mb: 2 }}
        />

        {/* Lista de Atletas */}
        {filteredAthletes.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography color="textSecondary">No se encontraron atletas disponibles.</Typography>
          </Box>
        ) : (
          <List sx={{ width: '100%', bgcolor: 'background.paper' }}>
            {filteredAthletes.map((athlete) => {
              const labelId = `checkbox-list-label-${athlete.id}`;
              const isSelected = selected.indexOf(athlete.id) !== -1;

              return (
                <ListItem
                  key={athlete.id}
                  button
                  onClick={handleToggle(athlete.id)}
                  secondaryAction={
                    <Checkbox
                      edge="end"
                      checked={isSelected}
                      inputProps={{ 'aria-labelledby': labelId }}
                    />
                  }
                >
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: isSelected ? '#F57C00' : '#bdbdbd' }}>
                        {athlete.nombre.charAt(0)}{athlete.apellido.charAt(0)}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    id={labelId}
                    primary={`${athlete.nombre} ${athlete.apellido}`}
                    secondary={
                        athlete.equipo_nombre ? 
                        `Actualmente en: ${athlete.equipo_nombre}` : 
                        "Sin Grupo asignado"
                    }
                  />
                </ListItem>
              );
            })}
          </List>
        )}
      </DialogContent>
      
      <DialogActions sx={{ p: 2, justifyContent: 'space-between' }}>
        <Typography variant="caption" sx={{ ml: 2 }}>
            {selected.length} seleccionados
        </Typography>
        <Box>
            <Button onClick={onClose} color="inherit" sx={{ mr: 1 }}>Cancelar</Button>
            <Button 
                onClick={handleSave} 
                variant="contained" 
                disabled={selected.length === 0 || loading}
                sx={{ bgcolor: '#F57C00', color: 'white' }}
            >
                {loading ? "Guardando..." : "Agregar Seleccionados"}
            </Button>
        </Box>
      </DialogActions>
    </Dialog>
  );
};

export default AddMemberModal;
