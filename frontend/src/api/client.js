import axios from 'axios';
import { tokenStore } from './tokenStore';
import { emitLogout } from './authEvents';

// 1. ESCALABILIDAD: Definimos la URL base dinámicamente.
// Si existe una variable de entorno (Producción), la usa. Si no, usa localhost.
// Back-compat: mantenemos soporte a VITE_API_URL, pero priorizamos VITE_API_BASE_URL.
const baseURL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const client = axios.create({
    baseURL: baseURL, // Apuntamos a la raíz, no a /api/ (para evitar duplicados)
    timeout: 10000,   // Esperamos máximo 10 seg antes de dar error (Robustez)
    headers: {
        'Content-Type': 'application/json',
        'accept': 'application/json'
    },
});

// Cliente “limpio” (sin interceptores) para refrescar tokens
const refreshClient = axios.create({
    baseURL: baseURL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
        'accept': 'application/json'
    },
});

// --- INTERCEPTOR DE REQUEST (SALIDA) ---
// Inyectamos el token automáticamente en cada petición
client.interceptors.request.use(
    (config) => {
        const token = tokenStore.getAccessToken();
        if (token) {
            config.headers = config.headers || {};
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

let isRefreshing = false;
let refreshSubscribers = [];

function subscribeTokenRefresh(cb) {
    refreshSubscribers.push(cb);
}

function onRefreshed(newAccessToken) {
    refreshSubscribers.forEach((cb) => cb(newAccessToken));
    refreshSubscribers = [];
}

function clearSessionAndNotify(reason) {
    tokenStore.clear();
    emitLogout(reason);
    // Fallback: si no hay subscriber (o el subscriber no navega), volvemos al login.
    if (typeof window !== 'undefined' && window.location?.pathname !== '/') window.location.href = '/';
}

// --- INTERCEPTOR DE RESPONSE (LLEGADA) ---
// Manejo centralizado de errores
client.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error) => {
        const originalRequest = error.config;

        // Si no tenemos response, propagamos (network error, CORS, etc.)
        if (!error.response) return Promise.reject(error);

        const status = error.response.status;
        const url = originalRequest?.url || '';

        // Evitar loops en endpoints de auth
        const isAuthEndpoint =
            url.includes('/api/token/') ||
            url.includes('/api/token/refresh/');

        // Si el error es 401 y no es auth endpoint, intentamos refresh una sola vez
        if (status === 401 && !isAuthEndpoint && originalRequest && !originalRequest._retry) {
            const refreshToken = tokenStore.getRefreshToken();
            if (!refreshToken) {
                clearSessionAndNotify('missing_refresh_token');
                return Promise.reject(error);
            }

            // Si ya hay un refresh en curso, nos colgamos a la cola
            if (isRefreshing) {
                return new Promise((resolve) => {
                    subscribeTokenRefresh((newAccessToken) => {
                        originalRequest._retry = true;
                        originalRequest.headers = originalRequest.headers || {};
                        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                        resolve(client(originalRequest));
                    });
                });
            }

            isRefreshing = true;

            try {
                const refreshResponse = await refreshClient.post('/api/token/refresh/', {
                    refresh: refreshToken,
                });

                const newAccessToken = refreshResponse.data?.access;
                const newRefreshToken = refreshResponse.data?.refresh;
                if (!newAccessToken) {
                    clearSessionAndNotify('refresh_missing_access');
                    return Promise.reject(error);
                }

                // Importante: SIMPLE_JWT puede rotar refresh tokens (ROTATE_REFRESH_TOKENS=True)
                tokenStore.setTokens({ access: newAccessToken, refresh: newRefreshToken });
                isRefreshing = false;
                onRefreshed(newAccessToken);

                originalRequest._retry = true;
                originalRequest.headers = originalRequest.headers || {};
                originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                return client(originalRequest);
            } catch (refreshErr) {
                isRefreshing = false;
                refreshSubscribers = [];
                clearSessionAndNotify('refresh_failed');
                return Promise.reject(refreshErr);
            }
        }

        return Promise.reject(error);
    }
);

export default client;
export const __internal = { refreshClient };
