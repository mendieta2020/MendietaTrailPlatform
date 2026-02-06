import React, { useState } from 'react';
import { 
    Box, Button, TextField, Typography, Paper, Alert 
} from '@mui/material';
import { styled } from '@mui/system';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Estilos personalizados
const BackgroundBox = styled(Box)({
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)',
    backgroundSize: 'cover',
});

const LoginPaper = styled(Paper)({
    padding: '40px',
    width: '100%',
    maxWidth: '400px',
    borderRadius: '16px',
    boxShadow: '0 8px 32px 0 rgba(31, 38, 135, 0.37)',
    textAlign: 'center',
});

const Login = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const location = useLocation();
    const { login } = useAuth();

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        
        try {
            const result = await login(username, password);
            if (!result?.success) {
                setError(result?.error || '❌ Usuario o contraseña incorrectos.');
                return;
            }

            // Redirigir a la ruta original (si venía de ProtectedRoute)
            const from = location.state?.from;
            const dest = from?.pathname ? `${from.pathname}${from.search || ''}` : '/dashboard';
            navigate(dest, { replace: true });

        } catch (err) {
            console.error(err);
            setError('❌ Usuario o contraseña incorrectos.');
        }
    };

    return (
        <BackgroundBox>
            <LoginPaper elevation={10}>
                <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1, color: '#333' }}>
                    Mendieta Trail 🏔️
                </Typography>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                    Plataforma de Alto Rendimiento
                </Typography>

                <Box component="form" onSubmit={handleLogin}>
                    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                    
                    <TextField
                        fullWidth
                        label="Usuario"
                        variant="outlined"
                        margin="normal"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                    />
                    <TextField
                        fullWidth
                        label="Contraseña"
                        type="password"
                        variant="outlined"
                        margin="normal"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />

                    <Button 
                        type="submit" 
                        fullWidth 
                        variant="contained" 
                        size="large"
                        sx={{ mt: 3, mb: 2, bgcolor: '#ff6b00', '&:hover': { bgcolor: '#e65100' } }}
                    >
                        Ingresar
                    </Button>
                </Box>
            </LoginPaper>
        </BackgroundBox>
    );
};

export default Login;
