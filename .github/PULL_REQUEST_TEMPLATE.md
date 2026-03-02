## Objective
<!-- Add a 1-sentence objective here -->

## Classification
- **Phase**: FASE 1 — Gates
- **Risk**: <!-- Low / Med / High -->

## Non-Negotiable Laws Checklist
- [ ] Multi-tenant untouched (no tenancy logic or org-scoping modified)
- [ ] OAuth untouched (Strava backward compatible)
- [ ] Plan ≠ Real untouched (domain models and reconciliation unchanged)
- [ ] No secrets logged (no PII or tokens introduced)

## Test Plan

**Backend:**
```bash
pytest -q
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
```

**Frontend:**
```bash
cd frontend
npm ci
npm run build
```

## Evidence
- [ ] CI/Actions run link: <!-- Paste link to successful GitHub Actions run -->
- [ ] Branch protection configured: 1 approval + required checks

## Rollback
Revert this PR (templates/workflows only). No data migrations.