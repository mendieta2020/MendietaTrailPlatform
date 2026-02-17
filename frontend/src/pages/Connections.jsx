import React, { useState, useEffect } from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Button,
    Alert,
    CircularProgress,
    Chip,
    Stack
} from '@mui/material';
import {
    CheckCircle,
    Error as ErrorIcon,
    Link as LinkIcon
} from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import client from '../api/client';

const Connections = () => {
    const [loading, setLoading] = useState(true);
    const [integrations, setIntegrations] = useState([]);
    const [userRole, setUserRole] = useState(null);
    const [alert, setAlert] = useState(null);
    const location = useLocation();
    const navigate = useNavigate();

    // Handle OAuth callback query params
    useEffect(() => {
        const params = new URLSearchParams(location.search);
        const status = params.get('status');
        const provider = params.get('provider');
        const error = params.get('error');
        const message = params.get('message');

        if (status === 'success' && provider) {
            setAlert({
                severity: 'success',
                message: `¡Conectado exitosamente con ${provider.charAt(0).toUpperCase() + provider.slice(1)}!`
            });
            // Clear query params
            navigate('/connections', { replace: true });
            // Refresh integrations
            fetchIntegrations();
        } else if (status === 'error') {
            setAlert({
                severity: 'error',
                message: message || `Error al conectar: ${error || 'unknown_error'}`
            });
            // Clear query params
            navigate('/connections', { replace: true });
        }
    }, [location.search, navigate]);

    // Fetch user role and integrations on mount
    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch user role
                const userRes = await client.get('/api/me');
                setUserRole(userRes.data.role);

                // Fetch integrations
                await fetchIntegrations();
            } catch (err) {
                console.error('Failed to fetch data:', err);
                setAlert({
                    severity: 'error',
                    message: 'Error al cargar las conexiones'
                });
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, []);

    const fetchIntegrations = async () => {
        try {
            const res = await client.get('/api/integrations/status');
            setIntegrations(res.data.integrations || []);
        } catch (err) {
            console.error('Failed to fetch integrations:', err);
        }
    };

    const handleConnect = async (provider) => {
        try {
            setLoading(true);
            const res = await client.post(`/api/integrations/${provider}/start`);

            // Redirect to OAuth URL
            const authUrl = res.data.authorization_url || res.data.oauth_url;
            if (authUrl) {
                window.location.href = authUrl;
            } else {
                setAlert({
                    severity: 'error',
                    message: 'Error: URL de autorización no disponible'
                });
            }
        } catch (err) {
            console.error('Failed to start OAuth flow:', err);
            const errorMsg = err.response?.data?.message || err.response?.data?.error || 'Error desconocido';
            setAlert({
                severity: 'error',
                message: `Error al iniciar conexión: ${errorMsg}`
            });
        } finally {
            setLoading(false);
        }
    };

    const getStatusChip = (integration) => {
        if (integration.connected) {
            return (
                <Chip
                    icon={<CheckCircle />}
                    label="Conectado"
                    color="success"
                    size="small"
                />
            );
        } else if (integration.error_reason) {
            return (
                <Chip
                    icon={<ErrorIcon />}
                    label="Error"
                    color="error"
                    size="small"
                />
            );
        } else {
            return (
                <Chip
                    label="No conectado"
                    variant="outlined"
                    size="small"
                />
            );
        }
    };

    const getActionButton = (integration) => {
        const isStrava = integration.provider === 'strava';
        const isEnabled = integration.enabled && isStrava; // Only Strava enabled for now

        if (!isEnabled) {
            return (
                <Button variant="outlined" disabled size="small">
                    Próximamente
                </Button>
            );
        }

        if (integration.connected) {
            return (
                <Button
                    variant="outlined"
                    color="primary"
                    size="small"
                    startIcon={<LinkIcon />}
                    onClick={() => handleConnect(integration.provider)}
                >
                    Reconectar
                </Button>
            );
        } else {
            return (
                <Button
                    variant="contained"
                    color="primary"
                    size="small"
                    startIcon={<LinkIcon />}
                    onClick={() => handleConnect(integration.provider)}
                >
                    Conectar con {integration.name}
                </Button>
            );
        }
    };

    if (loading && integrations.length === 0) {
        return (
            <Layout>
                <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
                    <CircularProgress />
                </Box>
            </Layout>
        );
    }

    return (
        <Layout>
            <Box>
                <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, mb: 1 }}>
                    Conexiones con Plataformas
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                    Conecta tus dispositivos y plataformas de entrenamiento para sincronizar actividades automáticamente.
                </Typography>

                {alert && (
                    <Alert severity={alert.severity} onClose={() => setAlert(null)} sx={{ mb: 3 }}>
                        {alert.message}
                    </Alert>
                )}

                <Stack spacing={2}>
                    {integrations.map((integration) => (
                        <Card key={integration.provider} sx={{ boxShadow: 2 }}>
                            <CardContent>
                                <Box display="flex" justifyContent="space-between" alignItems="center">
                                    <Box flex={1}>
                                        <Box display="flex" alignItems="center" gap={2} mb={1}>
                                            <Typography variant="h6" sx={{ fontWeight: 600 }}>
                                                {integration.name}
                                            </Typography>
                                            {getStatusChip(integration)}
                                        </Box>

                                        {integration.connected && integration.athlete_id && (
                                            <Typography variant="body2" color="text.secondary">
                                                ID de atleta: {integration.athlete_id}
                                            </Typography>
                                        )}

                                        {integration.error_reason && (
                                            <Alert severity="error" sx={{ mt: 1 }}>
                                                {integration.last_error || `Error: ${integration.error_reason}`}
                                            </Alert>
                                        )}

                                        {integration.last_sync_at && (
                                            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                                                Última sincronización: {new Date(integration.last_sync_at).toLocaleString('es-AR')}
                                            </Typography>
                                        )}
                                    </Box>

                                    <Box>
                                        {getActionButton(integration)}
                                    </Box>
                                </Box>
                            </CardContent>
                        </Card>
                    ))}
                </Stack>

                {integrations.length === 0 && (
                    <Alert severity="info">
                        No hay integraciones disponibles en este momento.
                    </Alert>
                )}
            </Box>
        </Layout>
    );
};

export default Connections;
