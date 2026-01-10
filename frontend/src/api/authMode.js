const rawValue = String(import.meta.env.VITE_USE_COOKIE_AUTH || '').toLowerCase();

export const USE_COOKIE_AUTH = rawValue === 'true';
