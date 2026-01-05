const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

// In-memory cache (mitiga lectura constante y permite borrar rápido en logout)
let accessToken = null;
let refreshToken = null;

function loadFromStorage() {
  // Blindaje: en algunos entornos (Safari privado, iframes restrictivos) localStorage puede lanzar.
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    if (accessToken === null) accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (refreshToken === null) refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch (e) {
    // Fallback seguro: tratamos como "sin sesión"
    accessToken = null;
    refreshToken = null;
  }
}

export const tokenStore = {
  keys: { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY },

  getAccessToken() {
    loadFromStorage();
    return accessToken;
  },

  getRefreshToken() {
    loadFromStorage();
    return refreshToken;
  },

  setTokens({ access, refresh }) {
    try {
      if (typeof access === 'string') {
        accessToken = access;
        if (typeof window !== 'undefined' && window.localStorage) localStorage.setItem(ACCESS_TOKEN_KEY, access);
      }
      if (typeof refresh === 'string') {
        refreshToken = refresh;
        if (typeof window !== 'undefined' && window.localStorage) localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
      }
    } catch (e) {
      // Si storage está bloqueado, mantenemos tokens en memoria.
      if (typeof access === 'string') accessToken = access;
      if (typeof refresh === 'string') refreshToken = refresh;
    }
  },

  clear() {
    accessToken = null;
    refreshToken = null;
    try {
      if (typeof window === 'undefined' || !window.localStorage) return;
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch (e) {
      // no-op
    }
  },
};
