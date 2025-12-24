# Frontend (React + Vite)

UI de coach/atleta para MendietaTrailPlatform. Este frontend consume el backend Django/DRF vía la capa HTTP en `src/api/client.js` (JWT + refresh automático).

## Configuración local (.env)

El frontend **siempre** usa `VITE_API_BASE_URL` como base URL para todas las llamadas al backend.

1) Crear un `.env` dentro de `frontend/`:

```bash
cp .env.example .env
```

2) Editar `frontend/.env`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Notas:
- También existe soporte legado para `VITE_API_URL`, pero `VITE_API_BASE_URL` tiene prioridad.
- El `baseURL` apunta a la raíz (no a `/api/`) para evitar duplicaciones en rutas.

## Correr el proyecto

```bash
npm install
npm run dev
```

## Troubleshooting (CORS/CSRF)

- Si ves errores de red/CORS en el navegador, verificá que el backend permita el origen del frontend (ej: `http://127.0.0.1:5173`).
- Este frontend usa **Authorization: Bearer** para JWT en cada request cuando hay token en `localStorage`.
