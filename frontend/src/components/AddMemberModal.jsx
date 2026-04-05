import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, List, ListItem, ListItemText, ListItemAvatar,
  Avatar, Checkbox, TextField, InputAdornment, Typography, Box, Chip
} from '@mui/material';
import { Search, PersonAdd } from '@mui/icons-material';
import client from '../api/client';

const AddMemberModal = ({ open, onClose, teamId, orgId, onMembersAdded }) => {
  const [athletes, setAthletes] = useState([]); // Todos los alumnos
  const [selected, setSelected] = useState([]); // IDs seleccionados
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchAvailableAthletes = useCallback(async () => {
    if (!orgId) return;
    try {
      const res = await client.get(`/api/p1/orgs/${orgId}/roster/athletes/`);
      const raw = Array.isArray(res.data) ? res.data : res.data?.results ?? [];
      const available = raw.filter(a => a.team_id !== parseInt(teamId));
      setAthletes(available);
    } catch (err) {
      console.error("Error cargando atletas:", err);
    }
  }, [teamId, orgId]);

  // 1. Cargar alumnos al abrir el modal
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
      const promises = selected.map(athleteId =>
        client.post(`/api/p1/orgs/${orgId}/teams/${teamId}/members/`, { athlete_id: athleteId })
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
    `${a.first_name} ${a.last_name}`.toLowerCase().includes(searchTerm.toLowerCase())
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
                    <Avatar sx={{ bgcolor: isSelected ? '#00D4AA' : '#bdbdbd' }}>
                      {(athlete.first_name || '?').charAt(0)}{(athlete.last_name || '').charAt(0)}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    id={labelId}
                    primary={`${athlete.first_name} ${athlete.last_name}`.trim() || athlete.email}
                    secondary={athlete.team_id ? "En otro grupo" : "Sin grupo asignado"}
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
            sx={{ bgcolor: '#00D4AA', color: 'white' }}
          >
            {loading ? "Guardando..." : "Agregar Seleccionados"}
          </Button>
        </Box>
      </DialogActions>
    </Dialog>
  );
};

export default AddMemberModal;