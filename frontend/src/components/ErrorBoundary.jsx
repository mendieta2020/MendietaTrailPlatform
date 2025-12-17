import React from 'react';
import { Paper, Typography, Box, Button } from '@mui/material';
import { ErrorOutline, Refresh } from '@mui/icons-material';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error("🔥 Error capturado por el Boundary:", error, errorInfo);
  }

  handleRetry = () => {
      this.setState({ hasError: false });
      window.location.reload();
  }

  render() {
    if (this.state.hasError) {
      return (
        <Paper 
            elevation={0} 
            sx={{ 
                p: 3, 
                borderRadius: 3, 
                height: this.props.height || 400, 
                border: '2px dashed #FECACA', 
                bgcolor: '#FEF2F2',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                textAlign: 'center'
            }}
        >
            <ErrorOutline sx={{ fontSize: 50, color: '#EF4444', mb: 2 }} />
            <Typography variant="subtitle1" fontWeight="bold" color="#991B1B">
                El gráfico no se pudo cargar.
            </Typography>
            <Typography variant="caption" color="#B91C1C" sx={{ mb: 2, display: 'block', maxWidth: 300 }}>
                Hubo un problema procesando los datos visuales. El resto de la aplicación funciona correctamente.
            </Typography>
             <Button 
                size="small"
                variant="outlined" 
                color="error" 
                startIcon={<Refresh />}
                onClick={this.handleRetry}
            >
                Recargar
            </Button>
        </Paper>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;