# Data Model — Plan ≠ Real

## Why the separation is fundamental

Confusing *intent* with *outcome* is the #1 source of coaching errors in software.
Quantoryn enforces a hard architectural boundary:

| Concept | Model | Source file | Description |
|---|---|---|---|
| **Planned** | `Entrenamiento` | `core/models.py:229` | What the coach prescribed: structure, zones, load target |
| **Planned blocks** | `BloqueEntrenamiento` | `core/models.py:302` | Interval/set breakdown within a session |
| **Planned steps** | `PasoEntrenamiento` | `core/models.py:308` | Individual execution steps |
| **Real** | `Actividad` | `core/models.py:326` | What the athlete actually did (provider-sourced) |
| **Real (foundation)** | `CompletedActivity` | `core/models.py` (PR-B) | Immutable ledger of raw completed activities per provider |

These two hierarchies **never collapse into one model**. Reconciliation is always explicit,
reversible, and versioned.

## Domain separation diagram

```
PLAN side                          REAL side
─────────────────────              ─────────────────────
Entrenamiento                      CompletedActivity
  .alumno FK                         .organization FK  (non-nullable)
  .fecha                             .alumno FK
  .tipo_deporte                      .sport
  .descripcion                       .start_time
  .estructura_json                   .duration_s
  .porcentaje_cumplimiento           .distance_m
  BloqueEntrenamiento                .elevation_gain_m
  PasoEntrenamiento                  .provider
                                     .provider_activity_id
                                     .raw_payload (JSON)
                                     .created_at
                                   Actividad  (canonical real)
                                     .source / source_object_id
                                     .canonical_load
                                     .reconciled_at
                                     .reconciliation_score
                                     .entrenamiento FK ← only link!
```

The `Actividad.entrenamiento` FK is the **only** bridge between the two sides, and it is
`null=True` — an activity that cannot be matched remains unreconciled rather than being
force-assigned to a plan.

## CompletedActivity — field reference

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `organization` | FK → User | **No** | Coach/org anchor. Fail-closed. |
| `alumno` | FK → Alumno | **No** | Athlete who performed activity |
| `sport` | CharField | No | Choices: `TIPO_ACTIVIDAD` (`core/models.py:28`) |
| `start_time` | DateTimeField | No | UTC |
| `duration_s` | IntegerField | No | Elapsed seconds |
| `distance_m` | FloatField | No | Metres (default 0.0) |
| `elevation_gain_m` | FloatField | **Yes** | Null = data unavailable from provider |
| `provider` | CharField | No | TextChoices: strava / garmin / coros / suunto / manual / other |
| `provider_activity_id` | CharField | No | Opaque provider ID |
| `raw_payload` | JSONField | No | Original provider blob (default `{}`) |
| `created_at` | DateTimeField | No | auto_now_add — ingestion timestamp |

### Idempotency constraint

```python
UniqueConstraint(
    fields=["organization", "provider", "provider_activity_id"],
    name="uniq_completed_activity_org_provider_id",
)
```

This means: the same provider activity can exist in multiple organisations (two coaches
whose athletes share a Strava activity), but within a single organisation the same
provider activity id is stored exactly once. Re-delivery is a no-op.

## Reconciliation

When the analytics engine matches a `CompletedActivity` / `Actividad` to an `Entrenamiento`:

1. `Actividad.entrenamiento` FK is set.
2. `Actividad.reconciled_at` is timestamped.
3. `Actividad.reconciliation_score` (0–1) records match confidence.
4. `Actividad.reconciliation_method` records the algorithm version string.
5. `Entrenamiento.porcentaje_cumplimiento` is recomputed — `core/compliance.py`.

If an athlete re-uploads or a provider corrects an activity, the reconciliation can be
re-run idempotently without data loss because the raw payload is preserved.

## Auditability and reproducibility

Scientific training metrics must be **traceable and re-computable**:

- `Actividad.datos_brutos` and `CompletedActivity.raw_payload` preserve the original
  provider JSON exactly as received.
- `canonical_load_method` and `load_version` on `Actividad` record which algorithm
  version produced the training load value — `core/models.py:415`.
- PMC (CTL/ATL/TSB) is computed from `canonical_load` values; changing the load
  formula increments `load_version` so historical values remain stable.
- All reconciliation runs are timestamped and scored — they can be replayed.

## Test coverage

| Test file | What it covers |
|---|---|
| `core/tests_completed_activity.py` | Model creation, unique constraint, multi-tenant isolation, plan≠real guard |
| `analytics/tests_pmc.py` | PMC computation from canonical load |
| `core/tests_canonical_load.py` | Canonical load method versioning |
| `analytics/tests_coach_tenancy.py` | Cross-tenant data isolation |
