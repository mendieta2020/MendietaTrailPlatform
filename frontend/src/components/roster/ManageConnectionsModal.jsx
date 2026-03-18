import React, { useCallback, useEffect, useReducer, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemSecondaryAction,
  ListItemText,
  MenuItem,
  Select,
  Snackbar,
  TextField,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { createExternalIdentity, deleteExternalIdentity, listExternalIdentities } from '../../api/p1';

const PROVIDERS = [
  { value: 'strava', label: 'Strava', color: '#FC4C02' },
  { value: 'suunto', label: 'Suunto', color: '#1A1A1A' },
];

function providerStyle(provider) {
  return PROVIDERS.find((p) => p.value === provider) ?? { label: provider, color: '#888' };
}

const initialState = { loading: false, error: null, identities: [] };

function reducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':
      return { ...state, loading: true, error: null };
    case 'FETCH_SUCCESS':
      return { loading: false, error: null, identities: action.identities };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export default function ManageConnectionsModal({ open, onClose, orgId }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [provider, setProvider] = useState('suunto');
  const [externalUserId, setExternalUserId] = useState('');
  const [alumnoId, setAlumnoId] = useState('');
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });

  const fetchIdentities = useCallback(() => {
    if (!orgId) return;
    dispatch({ type: 'FETCH_START' });
    listExternalIdentities(orgId)
      .then((res) => {
        dispatch({
          type: 'FETCH_SUCCESS',
          identities: res.data?.results ?? res.data ?? [],
        });
      })
      .catch(() =>
        dispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar las conexiones.' })
      );
  }, [orgId]);

  useEffect(() => {
    if (open) fetchIdentities();
  }, [open, fetchIdentities]);

  function showSnack(message, severity = 'success') {
    setSnackbar({ open: true, message, severity });
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!externalUserId.trim()) return;
    setCreating(true);
    try {
      const payload = {
        provider,
        external_user_id: externalUserId.trim(),
      };
      if (alumnoId.trim()) {
        payload.alumno_id = parseInt(alumnoId.trim(), 10);
      }
      await createExternalIdentity(orgId, payload);
      setExternalUserId('');
      setAlumnoId('');
      showSnack('Vinculación creada exitosamente.');
      fetchIdentities();
    } catch {
      showSnack('Error al crear la vinculación. Verifica los datos e intenta de nuevo.', 'error');
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id, providerLabel) {
    setDeletingId(id);
    try {
      await deleteExternalIdentity(orgId, id);
      showSnack(`Vinculación con ${providerLabel} eliminada.`);
      fetchIdentities();
    } catch {
      showSnack('Error al eliminar la vinculación.', 'error');
    } finally {
      setDeletingId(null);
    }
  }

  const linkedCount = state.identities.filter((i) => i.status === 'linked').length;

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            Gestión de Conexiones Externas
            {linkedCount > 0 && (
              <Chip label={`${linkedCount} activa${linkedCount !== 1 ? 's' : ''}`} size="small" color="success" />
            )}
          </Box>
        </DialogTitle>

        <DialogContent dividers>
          {/* Connections list */}
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Conexiones registradas
          </Typography>

          {state.loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
              <CircularProgress size={24} />
            </Box>
          )}

          {state.error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {state.error}
            </Alert>
          )}

          {!state.loading && !state.error && state.identities.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              No hay conexiones registradas en esta organización.
            </Typography>
          )}

          {!state.loading && state.identities.length > 0 && (
            <List dense disablePadding sx={{ mb: 2 }}>
              {state.identities.map((identity) => {
                const ps = providerStyle(identity.provider);
                return (
                  <ListItem key={identity.id} disableGutters>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Chip
                            label={ps.label}
                            size="small"
                            sx={{
                              bgcolor: ps.color,
                              color: '#fff',
                              fontWeight: 700,
                              fontSize: '0.68rem',
                            }}
                          />
                          <Typography variant="body2" component="span">
                            {identity.external_user_id}
                          </Typography>
                          <Chip
                            label={identity.status}
                            size="small"
                            variant="outlined"
                            color={identity.status === 'linked' ? 'success' : 'default'}
                            sx={{ fontSize: '0.65rem' }}
                          />
                        </Box>
                      }
                      secondary={
                        identity.alumno_id != null ? `Alumno ID: ${identity.alumno_id}` : 'Sin alumno asignado'
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton
                        size="small"
                        color="error"
                        disabled={deletingId === identity.id}
                        onClick={() => handleDelete(identity.id, ps.label)}
                      >
                        {deletingId === identity.id ? (
                          <CircularProgress size={16} />
                        ) : (
                          <DeleteIcon fontSize="small" />
                        )}
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                );
              })}
            </List>
          )}

          <Divider sx={{ my: 2 }} />

          {/* Create form */}
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Vincular nueva cuenta
          </Typography>
          <Box
            component="form"
            onSubmit={handleCreate}
            sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
          >
            <FormControl size="small" fullWidth>
              <InputLabel id="provider-select-label">Proveedor</InputLabel>
              <Select
                labelId="provider-select-label"
                value={provider}
                label="Proveedor"
                onChange={(e) => setProvider(e.target.value)}
              >
                {PROVIDERS.map((p) => (
                  <MenuItem key={p.value} value={p.value}>
                    {p.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              size="small"
              fullWidth
              label="ID de usuario externo"
              placeholder="ej: 12345678"
              value={externalUserId}
              onChange={(e) => setExternalUserId(e.target.value)}
              required
              helperText="ID del atleta en la plataforma del proveedor (ej. Suunto athlete ID)"
            />

            <TextField
              size="small"
              fullWidth
              label="Alumno ID (opcional)"
              placeholder="ej: 42"
              type="number"
              value={alumnoId}
              onChange={(e) => setAlumnoId(e.target.value)}
              helperText="ID interno del alumno en Quantoryn para vincular la cuenta"
            />

            <Button
              type="submit"
              variant="contained"
              disabled={creating || !externalUserId.trim()}
              startIcon={creating ? <CircularProgress size={16} color="inherit" /> : null}
            >
              Vincular
            </Button>
          </Box>
        </DialogContent>

        <DialogActions>
          <Button onClick={onClose}>Cerrar</Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </>
  );
}
