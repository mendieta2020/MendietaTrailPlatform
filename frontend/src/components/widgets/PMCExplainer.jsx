import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Button,
  Box,
} from '@mui/material';

export default function PMCExplainer({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>¿Qué es PMC?</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            El Performance Management Chart (PMC) resume la carga de entrenamiento en el tiempo.
          </Typography>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              CTL = Fitness
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Promedio ponderado de carga en semanas recientes.
            </Typography>
          </Box>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              ATL = Fatiga
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Carga de los últimos días: sube rápido con entrenamientos intensos.
            </Typography>
          </Box>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              TSB = Forma
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Diferencia entre Fitness y Fatiga (CTL - ATL).
            </Typography>
          </Box>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              ¿Cómo interpretarlo?
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Un TSB entre -10 y +10 suele indicar un estado “listo”. Valores muy negativos sugieren
              alta fatiga. El coach siempre decide: estas métricas son guía, no una regla fija.
            </Typography>
          </Box>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">Entendido</Button>
      </DialogActions>
    </Dialog>
  );
}
