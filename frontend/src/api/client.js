import axios from 'axios';

// 1. ESCALABILIDAD: Definimos la URL base dinámicamente.
// Si existe una variable de entorno (Producción), la usa. Si no, usa localhost.
const baseURL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

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
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
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

function clearSessionAndRedirect() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    if (window.location.pathname !== '/') window.location.href = '/';
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
            const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
            if (!refreshToken) {
                clearSessionAndRedirect();
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
                if (!newAccessToken) {
                    clearSessionAndRedirect();
                    return Promise.reject(error);
                }

                localStorage.setItem(ACCESS_TOKEN_KEY, newAccessToken);
                isRefreshing = false;
                onRefreshed(newAccessToken);

                originalRequest._retry = true;
                originalRequest.headers = originalRequest.headers || {};
                originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                return client(originalRequest);
            } catch (refreshErr) {
                isRefreshing = false;
                refreshSubscribers = [];
                clearSessionAndRedirect();
                return Promise.reject(refreshErr);
            }
        }

        return Promise.reject(error);
    }
);

export default client;