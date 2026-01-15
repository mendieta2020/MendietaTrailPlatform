# QA / Manual Verification (P0.2)

## Tests

Run the tenant isolation checks:

```bash
python manage.py test core analytics
```

## Manual verification (cross-tenant should return 404)

> Replace `<TOKEN>` with a valid coach JWT for Coach A and `<ATHLETE_ID_B>` with an athlete owned by Coach B.

```bash
curl -i -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/analytics/pmc/?alumno_id=<ATHLETE_ID_B>"
# Expect: HTTP/1.1 404
```

```bash
curl -i -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/analytics/summary/?alumno_id=<ATHLETE_ID_B>"
# Expect: HTTP/1.1 404
```

```bash
curl -i -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/activities/?athlete_id=<ATHLETE_ID_B>"
# Expect: HTTP/1.1 404
```

```bash
curl -i -H "Authorization: Bearer <TOKEN>" \
  "http://localhost:8000/api/analytics/alerts/?alumno_id=<ATHLETE_ID_B>"
# Expect: HTTP/1.1 404
```
