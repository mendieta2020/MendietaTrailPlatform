# QA: Integraciones Strava (Alumno)

## Configuración

Agregar en `frontend/.env.local`:

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Escenarios

1) **Alumno logueado → Conectar Strava**
   - Ir a `/athlete/integrations`.
   - Click en **Conectar con Strava**.
   - Verificar que la URL apunte a `http://127.0.0.1:8000/accounts/strava/login/?role=athlete`.
   - Confirmar que aparece la pantalla de autorización de Strava.

2) **Coach logueado → intentar conectar**
   - Desde el perfil del atleta (coach), usar **Invitar al alumno a conectar**.
   - Si el coach abre `/athlete/integrations`, debe ver mensaje de permisos (sin iniciar OAuth).
   - Si intenta `/accounts/strava/login/` directo, debe recibir 403.

3) **Flujos críticos no rotos**
   - Crear atleta.
   - Listar plantillas.
   - Asignar entrenamiento.
   - Completar onboarding básico.
