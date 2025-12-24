## Summary
- Conecta UI de Alertas con `GET /api/analytics/alerts/` (DRF) usando `src/api/client.js` (JWT + refresh).
- Agrega widget “Alertas” con tabs (Abiertas/Vistas), estados (loading/empty/error) y CTA mínimo “Ver todas”.
- Agrega página `/alerts` con filtros (Atleta + Estado) y paginación.

## Screenshots (pegar aquí)

### Dashboard (Alertas globales)
<!-- pegar screenshot -->

### AthleteDetail (Atleta #7, Abiertas)
<!-- pegar screenshot -->

### Alerts page (/alerts)
<!-- pegar screenshot -->

## Test plan
- [ ] `npm test` en `frontend/`
- [ ] Dashboard: widget muestra alertas (top 5) y cambia Abiertas/Vistas
- [ ] AthleteDetail `/athletes/7`: “Abiertas” muestra la alerta sembrada (si existe)
- [ ] `/alerts`: filtros (Atleta + Estado) + paginación funcionan

