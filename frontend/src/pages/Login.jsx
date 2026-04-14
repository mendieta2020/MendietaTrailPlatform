import React, { useState } from 'react';
import {
    Box, Button, TextField, Typography, Paper, Alert,
} from '@mui/material';
import { styled } from '@mui/system';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import QuantorynLogo from '../components/QuantorynLogo';

// Estilos personalizados
const BackgroundBox = styled(Box)({
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0D1117 0%, #1A2332 100%)',
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
    const [searchParams] = useSearchParams();
    // Pre-fill email from ?email= query param (post password-recovery redirect)
    const [email, setEmail] = useState(() => {
        const prefill = searchParams.get('email');
        return prefill ? decodeURIComponent(prefill) : '';
    });
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const location = useLocation();
    const { login } = useAuth();

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');

        try {
            const result = await login(email, password);
            if (!result?.success) {
                setError(result?.error || '❌ Email o contraseña incorrectos.');
                return;
            }

            // Redirigir a la ruta original (si venía de ProtectedRoute)
            const from = location.state?.from;
            const dest = from?.pathname ? `${from.pathname}${from.search || ''}` : '/dashboard';
            navigate(dest, { replace: true });

        } catch (err) {
            console.error(err);
            setError('❌ Email o contraseña incorrectos.');
        }
    };

    return (
        <BackgroundBox>
            <LoginPaper elevation={10}>
                <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1.5 }}>
                    <QuantorynLogo size={48} />
                </Box>
                <Typography variant="h5" sx={{ fontWeight: 800, mb: 0.5, color: '#0D1117', letterSpacing: '0.08em' }}>
                    QUANTORYN
                </Typography>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                    Coaching Deportivo Basado en Evidencia
                </Typography>

                {location.state?.resetSuccess && (
                    <Alert severity="success" sx={{ mb: 2 }}>
                        ¡Contraseña actualizada! Ingresá con tu nueva contraseña.
                    </Alert>
                )}

                <Box component="form" onSubmit={handleLogin}>
                    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

                    <TextField
                        fullWidth
                        label="Email"
                        type="email"
                        variant="outlined"
                        margin="normal"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        autoComplete="email"
                    />
                    <TextField
                        fullWidth
                        label="Contraseña"
                        type="password"
                        variant="outlined"
                        margin="normal"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="current-password"
                    />

                    <Button
                        type="submit"
                        fullWidth
                        variant="contained"
                        size="large"
                        sx={{ mt: 3, mb: 1, bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, '&:hover': { bgcolor: '#00BF99' } }}
                    >
                        Ingresar
                    </Button>
                    <Box sx={{ textAlign: 'right', mt: 1 }}>
                        <Link to="/auth/forgot-password" style={{ fontSize: 14, color: '#00D4AA', textDecoration: 'none' }}>
                            ¿Olvidaste tu contraseña?
                        </Link>
                    </Box>
                </Box>
            </LoginPaper>
        </BackgroundBox>
    );
};

export default Login;
