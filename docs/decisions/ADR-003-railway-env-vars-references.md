# ADR-003 — Railway internal service env vars must be dynamic references

- Status: accepted
- Date: 2026-04-22
- Deciders: Fernando Mendieta
- Related: Constitution Law 6 (secrets handling), Law 8 (CI/production stability)

## Context and problem statement

Two production incidents in 48 hours, both caused by the same root cause:

- **2026-04-21**: After rotating Postgres password in Railway UI, backend service (`MendietaTrailPlatform`) failed to reconnect because `DB_PASSWORD` was stored as a hardcoded string instead of a dynamic reference. Fixed manually.
- **2026-04-22**: After rotating Postgres password again, worker service (`agile-alignment`) failed with `psycopg2.OperationalError: password authentication failed`. All async tasks crashed: Strava backfill, MercadoPago webhook reconciliation, PMC recompute. Root cause: `DB_PASSWORD` in worker was still hardcoded (fix in 2026-04-21 only covered backend).

This matches Railway's own incident pattern from the February 2026 outage report, where services with hardcoded credentials failed to auto-recover when Railway rotated credentials during platform recovery.

## Considered options

1. **Native Railway references** (`${{Service.VAR}}`) — free, built-in, officially recommended.
2. **`railway.json` (Config as Code)** — versions build config but not secrets; complement, not replacement.
3. **Doppler** — cloud secret manager, simpler UX, monthly cost, cloud-only.
4. **Infisical** — OSS self-hosted, secret rotation automation, operational overhead.
5. **HashiCorp Vault** — enterprise dynamic credentials, overkill for current scale.

## Decision

All environment variables in Railway services that reference **Railway-internal services** (Postgres, Redis, future Railway databases) MUST use Railway's dynamic reference syntax `${{Service.VAR}}`.

External API secrets — credentials issued by third-party providers — remain as static values. They cannot be references because their source of truth lives outside Railway.

### Scope by variable category

| Category | Pattern | Rationale |
|---|---|---|
| Postgres credentials | `${{Postgres.PGHOST}}`, `${{Postgres.PGUSER}}`, `${{Postgres.PGPASSWORD}}`, `${{Postgres.PGDATABASE}}`, `${{Postgres.PGPORT}}`, `${{Postgres.DATABASE_URL}}` | Auto-rotated by Railway on password regenerate |
| Redis credentials | `${{Redis.REDIS_URL}}` | Same as Postgres |
| Celery broker / result backend | `${{Redis.REDIS_URL}}` | Depends on Redis |
| External API keys (Strava, MP, Resend, Google, OpenAI, Sentry) | Static value | Third-party source of truth; rotated manually (see runbook §4) |
| App config (DEBUG, ALLOWED_HOSTS, CORS, CSRF, FRONTEND_URL, BACKEND_URL) | Static value | Not secrets |
| Django SECRET_KEY | Static value | Session-invalidating if rotated; handle with care per runbook |

## Consequences

**Positive**:
- Password rotation = zero downtime. Validated by smoke test 2026-04-22.
- No manual credential synchronization across services on rotation.
- Railway-official best practice.
- Bus factor improved: rotation is no longer tribal knowledge.

**Negative**:
- Requires discipline on every new variable — cannot be enforced by code (variables live in Railway UI, not in repo).
- Mitigation: runbook includes a quarterly audit procedure.

## Re-evaluation triggers

This decision must be revisited if any of the following occurs:

- Railway deprecates or changes the `${{Service.VAR}}` reference syntax.
- The project migrates off Railway (new platform needs an equivalent pattern).
- Staging or preview environments are added (may justify Doppler or Infisical for multi-env secret management).
- A quarterly dry-run reveals the runbook is outdated. A stale runbook is worse than no runbook.

**Quarterly dry-run requirement**: runbook procedures must be tested every 90 days in a non-critical window. If a documented procedure no longer matches reality, fix the runbook or revisit this ADR before the next rotation.

## Sources

- [Railway Variables documentation](https://docs.railway.com/variables) — official recommendation for dynamic references
- [Railway Best Practices](https://docs.railway.com/overview/best-practices)
- [Railway Blog — Database Reference Variables](https://blog.railway.com/p/database-reference-variables)
- [Railway Incident Report — February 11 2026](https://blog.railway.com/p/incident-report-february-11-2026)
- [Martin Fowler — Architecture Decision Records](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)
