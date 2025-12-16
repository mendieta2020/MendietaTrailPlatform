import axios from 'axios';

// 1. ESCALABILIDAD: Definimos la URL base dinámicamente.
// Si existe una variable de entorno (Producción), la usa. Si no, usa localhost.
const baseURL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const client = axios.create({
    baseURL: baseURL, // Apuntamos a la raíz, no a /api/ (para evitar duplicados)
    timeout: 10000,   // Esperamos máximo 10 seg antes de dar error (Robustez)
    headers: {
        'Content-Type': 'application/json',
        'accept': 'application/json'
    },
});

// --- INTERCEPTOR DE REQUEST (SALIDA) ---
// Inyectamos el token automáticamente en cada petición
client.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// --- INTERCEPTOR DE RESPONSE (LLEGADA) ---
// Manejo centralizado de errores
client.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error) => {
        const originalRequest = error.config;

        // Si el error es 401 (No Autorizado) y no hemos reintentado aún
        if (error.response && error.response.status === 401 && !originalRequest._retry) {
            
            // NOTA CTO: Aquí en la Fase 6 implementaremos la lógica de "Refresh Token"
            // para renovar la sesión sin sacar al usuario.
            // Por ahora, por seguridad, cerramos sesión limpiamente.
            
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            
            // Redirigimos al Login si no estamos ya allí
            if (window.location.pathname !== '/') {
                window.location.href = '/';
            }
        }
        return Promise.reject(error);
    }
);

export default client;