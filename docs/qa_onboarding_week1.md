# QA Onboarding (Week 1)

## Overview
El onboarding ahora usa un flujo nativo con MUI (Dialog + Stepper + Popover). No depende de `react-joyride` y es tolerante a widgets ausentes.

## Manual QA checklist
1. Abrir `http://localhost:5173/dashboard?onboarding=1` con un usuario coach autenticado.
2. Paso **Conecta Strava**:
   - El botón **Conectar con Strava** apunta a `/accounts/strava/login/`.
   - Se puede avanzar sin conectar.
3. Paso **Crea tu primer atleta**:
   - Crear un atleta con nombre y apellido.
   - Verificar que aparezca un mensaje de éxito.
4. Paso **Asigna una plantilla**:
   - Seleccionar una plantilla en el selector.
   - Asignar al atleta creado con fecha de hoy.
5. Paso **Explora PMC y alertas**:
   - Click en **Ver Rendimiento Fisiológico (PMC)** y **Ver Alertas y Riesgos**.
   - Si el widget no está visible, aparece un aviso en el popover.
6. Paso **Finaliza onboarding**:
   - Click en **Finalizar** envía `POST /api/onboarding/complete/` y cierra el wizard.

## Notes
- Los widgets se anclan a `#pmc-widget` y `#alerts-widget` en el Dashboard.
- El wizard no bloquea el uso normal del panel si se cierra.
