# PR-S1 Seguridad - Nota de despliegue

## Cambios clave
- Swagger protegido por permiso staff + flag `SWAGGER_ENABLED`.
- Throttling DRF activado en endpoints sensibles (tokens, webhooks Strava, coach, analytics).
- SimpleJWT: habilitada app `token_blacklist` para respaldar `BLACKLIST_AFTER_ROTATION=True`.

## Variables/flags
- `SWAGGER_ENABLED` (default: `True` solo si `DEBUG=True`; en prod es `False`).
- `USE_COOKIE_AUTH` (ya existente): preferir cookies HttpOnly en prod.
- `COOKIE_AUTH_SECURE`, `COOKIE_AUTH_SAMESITE`, `COOKIE_AUTH_DOMAIN` (ya existentes).

## Migraciones
- Requiere ejecutar `python manage.py migrate` para crear tablas de `token_blacklist`.

## Comandos post-deploy
- `python manage.py migrate`
- (opcional) `python manage.py check`

## Postura de auth (prod)
- Mantener JWT vía cookies HttpOnly (sin localStorage).
- Limitar exposición de Swagger a staff o deshabilitar en prod (`SWAGGER_ENABLED=False`).
