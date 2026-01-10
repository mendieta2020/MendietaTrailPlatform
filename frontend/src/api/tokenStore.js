import { USE_COOKIE_AUTH } from './authMode';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

// In-memory cache (mitiga lectura constante y permite borrar rápido en logout)
let accessToken = null;
let refreshToken = null;

function loadFromStorage() {
  if (accessToken === null) accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (refreshToken === null) refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
}

export const tokenStore = {
  keys: { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY },

  getAccessToken() {
    if (USE_COOKIE_AUTH) return null;
    loadFromStorage();
    return accessToken;
  },

  getRefreshToken() {
    if (USE_COOKIE_AUTH) return null;
    loadFromStorage();
    return refreshToken;
  },

  setTokens({ access, refresh }) {
    if (USE_COOKIE_AUTH) {
      // TODO: eliminar localStorage cuando la migración a cookies esté completa.
      this.clear();
      return;
    }
    if (typeof access === 'string') {
      accessToken = access;
      localStorage.setItem(ACCESS_TOKEN_KEY, access);
    }
    if (typeof refresh === 'string') {
      refreshToken = refresh;
      localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    }
  },

  clear() {
    accessToken = null;
    refreshToken = null;
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};
