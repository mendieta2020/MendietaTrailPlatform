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
    Stack,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Tooltip
} from '@mui/material';
import {
    CheckCircle,
    Error as ErrorIcon,
    Link as LinkIcon,
    PhoneIphone,
    NotificationsNone
} from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import client from '../api/client';

// Providers that require a native mobile app instead of web OAuth
const MOBILE_ONLY_PROVIDERS = ['apple_health'];

const Connections = () => {
    const [loading, setLoading] = useState(true);
    const [integrations, setIntegrations] = useState([]);
    const [userRole, setUserRole] = useState(null);
    const [alert, setAlert] = useState(null);
    // Avisarme modal state
    const [avisarmeProvider, setAvisarmeProvider] = useState(null);
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
        const isMobileOnly = MOBILE_ONLY_PROVIDERS.includes(integration.provider);

        if (isMobileOnly) {
            return (
                <Chip
                    icon={<PhoneIphone />}
                    label="App iOS"
                    color="default"
                    size="small"
                    variant="outlined"
                />
            );
        }
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

    const getSubtitle = (integration) => {
        if (MOBILE_ONLY_PROVIDERS.includes(integration.provider)) {
            return 'Requiere app iOS con HealthKit. No disponible como integración web.';
        }
        if (!integration.enabled) {
            return 'Próximamente: esta integración aún no está disponible.';
        }
        return null;
    };

    const getActionButton = (integration) => {
        const isMobileOnly = MOBILE_ONLY_PROVIDERS.includes(integration.provider);

        // Apple Health / mobile-only: different CTA — not OAuth
        if (isMobileOnly) {
            return (
                <Tooltip title="Esta integración requiere la app iOS de MTP con HealthKit." arrow>
                    <span>
                        <Button
                            variant="outlined"
                            size="small"
                            disabled
                            startIcon={<PhoneIphone />}
                        >
                            Requiere app
                        </Button>
                    </span>
                </Tooltip>
            );
        }

        // Disabled (Coming Soon) providers
        if (!integration.enabled) {
            return (
                <Box display="flex" flexDirection="column" alignItems="flex-end" gap={0.5}>
                    <Button variant="outlined" disabled size="small">
                        Próximamente
                    </Button>
                    <Button
                        size="small"
                        variant="text"
                        color="secondary"
                        startIcon={<NotificationsNone fontSize="small" />}
                        sx={{ fontSize: '0.72rem', textTransform: 'none', p: 0, minWidth: 0 }}
                        onClick={() => setAvisarmeProvider(integration)}
                    >
                        Avisarme
                    </Button>
                </Box>
            );
        }

        // Enabled + connected → Reconectar
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
        }

        // Enabled + not connected → Connect CTA
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
                    {integrations.map((integration) => {
                        const subtitle = getSubtitle(integration);
                        return (
                            <Card
                                key={integration.provider}
                                sx={{
                                    boxShadow: 2,
                                    opacity: integration.enabled ? 1 : 0.82,
                                }}
                            >
                                <CardContent>
                                    <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                                        <Box flex={1}>
                                            <Box display="flex" alignItems="center" gap={2} mb={0.5}>
                                                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                                                    {integration.name}
                                                </Typography>
                                                {getStatusChip(integration)}
                                            </Box>

                                            {/* Helper text for disabled / mobile-only providers */}
                                            {subtitle && (
                                                <Typography
                                                    variant="caption"
                                                    color="text.disabled"
                                                    display="block"
                                                    sx={{ mb: 1 }}
                                                >
                                                    {subtitle}
                                                </Typography>
                                            )}

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

                                        <Box ml={2} mt={0.5}>
                                            {getActionButton(integration)}
                                        </Box>
                                    </Box>
                                </CardContent>
                            </Card>
                        );
                    })}
                </Stack>

                {integrations.length === 0 && (
                    <Alert severity="info">
                        No hay integraciones disponibles en este momento.
                    </Alert>
                )}
            </Box>

            {/* Avisarme modal — no backend call, purely informational */}
            <Dialog
                open={Boolean(avisarmeProvider)}
                onClose={() => setAvisarmeProvider(null)}
                maxWidth="xs"
                fullWidth
            >
                <DialogTitle sx={{ pb: 1 }}>
                    Te avisaremos cuando esté listo
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body2" color="text.secondary">
                        La integración con{' '}
                        <strong>{avisarmeProvider?.name}</strong>{' '}
                        está en nuestro roadmap. Te notificaremos dentro de la plataforma
                        cuando esté disponible.
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setAvisarmeProvider(null)} variant="contained" size="small">
                        Entendido
                    </Button>
                </DialogActions>
            </Dialog>
        </Layout>
    );
};

export default Connections;
