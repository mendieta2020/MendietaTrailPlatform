# Task Capsule — PR-004: Django Security Headers

> **Phase:** P0 · **Risk:** Low
> **Branch:** `p0/django-security-headers`
> **Scope:** Backend only — documentation + settings only

---

## Objective

Harden the Django backend HTTP response surface by enabling standard security headers via Django's built-in middleware and settings. This closes common web security gaps (clickjacking, MIME sniffing, referrer leakage) without touching application logic, models, or the OAuth/tenancy critical path.

---

## Classification

| Dimension | Value |
|-----------|-------|
| Phase | P0 |
| Risk | Low |
| Blast radius | Settings only — no model, view, or integration changes |
| Reversibility | High — settings can be reverted in one line each |
| CI impact | Build + lint only; no test logic changes |

---

## Allowed Files (Allowlist)

Only these files may be modified in this PR:

```
backend/config/settings/base.py
backend/config/settings/production.py
backend/config/settings/local.py   ← only if a dev override is needed
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to `urls.py`, views, models, serializers, or migrations.
- No changes to `integrations/`.
- No changes to `frontend/`.
- No changes to `.github/workflows/`.
- No changes to `OAuthCredential`, `ExternalIdentity`, or any OAuth-related view.
- Do not add new middleware unless it is a standard Django built-in (`django.middleware.*`).

---

## Blast Radius Notes

- **No tenancy risk.** Headers are applied globally at the HTTP layer.
- **No OAuth risk.** Headers do not affect OAuth callback URLs or token flow.
- **Potential breakage:** `X-Frame-Options: DENY` can break embedded iframes. Verify the frontend has no iframe dependencies before enabling. If uncertain, use `SAMEORIGIN` as the safe default.
- **CSP (Content Security Policy) is out of scope for this PR.** It requires frontend audit and carries high breakage risk. Do not add it here.

---

## Implementation Plan

### Step 1 — Verify existing middleware order

Open `backend/config/settings/base.py`. Confirm `SecurityMiddleware` is present and is the **first** entry in `MIDDLEWARE`. If not, add it as the first entry.

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # ... rest of middleware
]
```

### Step 2 — Add security settings to `base.py`

Add or confirm the following settings. Use comments to document intent.

```python
# Security headers — PR-004
SECURE_CONTENT_TYPE_NOSNIFF = True        # X-Content-Type-Options: nosniff
SECURE_BROWSER_XSS_FILTER = True          # Legacy X-XSS-Protection (safe to include)
X_FRAME_OPTIONS = "SAMEORIGIN"            # Clickjacking protection; use DENY if no iframes
REFERRER_POLICY = "strict-origin-when-cross-origin"  # Referrer-Policy header
```

### Step 3 — Add HTTPS-only settings to `production.py`

These must only be enabled in production to avoid breaking local development.

```python
# HTTPS enforcement — PR-004
SECURE_SSL_REDIRECT = True                # Redirect HTTP → HTTPS
SECURE_HSTS_SECONDS = 31536000           # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True             # Cookies over HTTPS only
CSRF_COOKIE_SECURE = True
```

> ⚠️ **HSTS warning:** Once HSTS is deployed, browsers enforce HTTPS for `SECURE_HSTS_SECONDS`. Start with a short value (e.g., `3600`) in the first deploy, verify, then increase to `31536000`. Document this in the PR description.

### Step 4 — Verify local settings safety

Confirm `local.py` overrides `SECURE_SSL_REDIRECT = False` and `SESSION_COOKIE_SECURE = False` to prevent local breakage.

---

## Test Plan

Run in this order:

```bash
# 1. Django system check (catches settings errors immediately)
python manage.py check --deploy

# 2. Full backend test suite
python -m pytest -q

# 3. Manual smoke: confirm headers present in HTTP response
curl -I http://localhost:8000/api/
# Expect: X-Content-Type-Options, X-Frame-Options in response headers
```

No new test files are required for this PR. The `--deploy` check is the primary validation gate.

---

## Definition of Done

- [ ] `SecurityMiddleware` is first in `MIDDLEWARE`
- [ ] `SECURE_CONTENT_TYPE_NOSNIFF = True` in `base.py`
- [ ] `X_FRAME_OPTIONS` set in `base.py`
- [ ] `REFERRER_POLICY` set in `base.py`
- [ ] HTTPS settings in `production.py` only
- [ ] Local settings do not enable HTTPS redirects
- [ ] `python manage.py check --deploy` passes with no warnings
- [ ] `python -m pytest -q` green
- [ ] CI green on push
- [ ] PR description documents HSTS ramp-up plan

---

## Rollback Strategy

1. Revert the settings changes in `base.py` and `production.py`.
2. Redeploy. Headers are removed immediately on next request.
3. No migrations required; no DB state affected.
4. HSTS cannot be "unset" in browsers that have already cached it — this is why the ramp-up plan matters.

---

*Capsule last updated: 2026-03-06 · See also: `docs/ai/CONSTITUTION.md`, `docs/ai/REPO_MAP.md`*
