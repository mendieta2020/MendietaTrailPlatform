import React from 'react';
import { 
  Paper, Typography, List, ListItem, ListItemAvatar, 
  ListItemText, Avatar, Chip, Box, Divider 
} from '@mui/material';
import { AttachMoney, AccessTime, CheckCircle } from '@mui/icons-material';

const PaymentsWidget = ({ pagos }) => {
  return (
    <Paper sx={{ p: 2, height: '100%', borderRadius: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
          Últimos Ingresos 💵
        </Typography>
        <Chip label="Este Mes" size="small" color="primary" variant="outlined" />
      </Box>

      {pagos.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
          <Typography variant="body2">No hay pagos registrados aún.</Typography>
        </Box>
      ) : (
        <List>
          {pagos.slice(0, 5).map((pago, index) => (
            <React.Fragment key={pago.id}>
              <ListItem alignItems="flex-start" disablePadding sx={{ py: 1 }}>
                <ListItemAvatar>
                  <Avatar sx={{ bgcolor: pago.es_valido ? '#e8f5e9' : '#fff3e0' }}>
                    {pago.es_valido ? 
                      <CheckCircle sx={{ color: '#2e7d32' }} /> : 
                      <AccessTime sx={{ color: '#ed6c02' }} />
                    }
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                      {/* Aquí luego pondremos el nombre real del alumno */}
                      Alumno #{pago.alumno || '?'}
                    </Typography>
                  }
                  secondary={
                    <Typography variant="caption" color="text.secondary">
                      {new Date(pago.fecha_pago).toLocaleDateString()} via {pago.metodo}
                    </Typography>
                  }
                />
                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: '#2e7d32' }}>
                  +${parseFloat(pago.monto).toLocaleString()}
                </Typography>
              </ListItem>
              {index < pagos.length - 1 && <Divider variant="inset" component="li" />}
            </React.Fragment>
          ))}
        </List>
      )}
    </Paper>
  );
};

export default PaymentsWidget;