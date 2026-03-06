# Task Capsule — PR-005: Vercel Security Headers (Frontend)

> **Phase:** P0 · **Risk:** Low
> **Branch:** `p0/vercel-security-headers`
> **Scope:** Frontend config only — `vercel.json` / Vite config only

---

## Objective

Add HTTP security headers to the Vercel-hosted React/Vite frontend. These headers protect users against clickjacking, MIME sniffing, and referrer leakage at the CDN/edge layer, independent of the Django backend. This is a config-only change with no application logic impact.

---

## Classification

| Dimension | Value |
|-----------|-------|
| Phase | P0 |
| Risk | Low |
| Blast radius | Frontend delivery config only — no component, hook, or store changes |
| Reversibility | High — `vercel.json` change, redeployable in seconds |
| CI impact | Frontend build + lint check only |

---

## Allowed Files (Allowlist)

Only these files may be modified in this PR:

```
vercel.json                    ← primary target
frontend/vite.config.js        ← only if dev-server headers are needed for parity
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to any React component, hook, context, or store.
- No changes to `frontend/src/`.
- No changes to backend settings, `urls.py`, or middleware.
- No changes to `integrations/`.
- No changes to `.github/workflows/`.
- Do not add Content Security Policy (CSP) in this PR — it requires a full frontend audit.

---

## Blast Radius Notes

- **No tenancy risk.** Headers are applied globally at the edge layer.
- **No OAuth risk.** These headers do not interfere with the Strava OAuth flow as long as redirect URIs remain unchanged.
- **Potential breakage:** `X-Frame-Options: DENY` will break any page embedded in an iframe. Use `SAMEORIGIN` if unsure. Confirm the product has no embedded use cases before using `DENY`.
- **CSP is out of scope.** A malformed CSP blocks all scripts/styles. It must be a separate, carefully audited PR.

---

## Implementation Plan

### Step 1 — Locate or create `vercel.json`

Check if `vercel.json` exists at the repo root. If it exists, open it and note existing config. If it does not exist, create it.

> Open maximum 1 file before acting. Do not explore the rest of the frontend.

### Step 2 — Add security headers block

Add a `headers` block targeting all routes (`"source": "/(.*)"`) with the following headers:

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "X-Content-Type-Options",
          "value": "nosniff"
        },
        {
          "key": "X-Frame-Options",
          "value": "SAMEORIGIN"
        },
        {
          "key": "Referrer-Policy",
          "value": "strict-origin-when-cross-origin"
        },
        {
          "key": "Permissions-Policy",
          "value": "camera=(), microphone=(), geolocation=()"
        }
      ]
    }
  ]
}
```

Merge into any existing `vercel.json` structure without removing existing keys (rewrites, redirects, functions, etc.).

### Step 3 — Vite dev-server parity (optional, low priority)

If local development parity is desired, add matching headers to `frontend/vite.config.js` under `server.headers`. This is optional and does not affect production.

### Step 4 — Verify build still passes

```bash
cd frontend
npm run lint
npm run build
```

---

## Test Plan

```bash
# 1. Frontend lint
cd frontend && npm run lint

# 2. Frontend build (validates no breakage)
cd frontend && npm run build

# 3. Post-deploy verification (after Vercel preview deployment)
curl -I https://<preview-url>.vercel.app/
# Expect: X-Content-Type-Options, X-Frame-Options, Referrer-Policy in response
```

No new test files required. Post-deploy header verification via `curl` or browser DevTools → Network → response headers.

---

## Definition of Done

- [ ] `vercel.json` includes headers block for `/(.*)`
- [ ] `X-Content-Type-Options: nosniff` present
- [ ] `X-Frame-Options: SAMEORIGIN` present
- [ ] `Referrer-Policy: strict-origin-when-cross-origin` present
- [ ] `Permissions-Policy` set to deny sensitive APIs
- [ ] No existing `vercel.json` keys removed or broken
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] CI green on push
- [ ] Vercel preview deployment shows headers in response (verified via curl or DevTools)

---

## Rollback Strategy

1. Remove or revert the `headers` block in `vercel.json`.
2. Trigger a Vercel redeployment (push or manual redeploy).
3. Headers are removed immediately on next CDN response.
4. No database state, no migrations, no backend changes involved.

---

*Capsule last updated: 2026-03-06 · See also: `docs/ai/CONSTITUTION.md`, `docs/ai/REPO_MAP.md`*
