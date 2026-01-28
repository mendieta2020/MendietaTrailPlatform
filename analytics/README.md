# Analytics pipeline (overview)

## Flujo actual (Strava → Actividad → Analytics)

1. **Webhook Strava** (`core.tasks.process_strava_event`)
   - Se normaliza el payload (`core.strava_mapper.normalize_strava_activity`)
   - Se decide creación (`core.strava_activity_normalizer.decide_activity_creation`)
   - Se persiste `core.Actividad` vía `core.actividad_upsert.upsert_actividad`
   - Se calculan carga canónica (PR6) y **calorías estimadas** si no llegan de Strava (`core.calories.compute_calories_kcal`)

2. **Recompute analytics** (`analytics.tasks.recompute_pmc_from_activities`)
   - Reconstruye `analytics.DailyActivityAgg` desde `core.Actividad`
   - Calcula `load`, `distance_m`, `duration_s`, `elev_gain_m` y **calories_kcal**
   - Recalcula `PMCHistory` (PMC/CTL/ATL/TSB)

3. **Week Summary / Dashboard**
   - Agrega `DailyActivityAgg` para endpoints como:
     - `/api/coach/athletes/{id}/week-summary/`
     - dashboards del atleta

## Riesgos identificados (antes del fix)

- `analytics_dailyactivityagg.calories_kcal` era **NOT NULL** en BD, pero:
  - `DailyActivityAgg` no lo incluía en el modelo
  - El builder (`pmc_engine.build_daily_aggs_for_alumno`) no lo populaba
  - Resultado: `IntegrityError` al hacer `bulk_create`

- `core.Actividad.calories_kcal` podía quedar `NULL` si Strava no enviaba calorías.
  - Sin una política de fallback, los agregados quedaban con `NULL` o rompían el pipeline.

## Política de calorías (v1)

- **Fuente primaria**: calorías provistas por Strava (si son válidas >0).
- **Fallback estimado**:
  - RUN/TRAIL: ~1.0 kcal/kg/km
  - WALK: ~0.75 kcal/kg/km
  - BIKE: MET 6.8 (moderado) → kcal = MET × kg × horas
  - OTHER: MET 3.5 si hay duración; si no, 0

Esta política se aplica tanto en la ingesta (Actividad) como en la generación
de `DailyActivityAgg`, garantizando valores numéricos y evitando `NULL` en
campos críticos.

## PMC endpoint contract + scale risks

### Contract (GET `/api/analytics/pmc/`)
- **Output**: lista ordenada por fecha ascendente.
- **Keys por fila**:
  - `fecha` (string `YYYY-MM-DD`)
  - `is_future` (bool)
  - `ctl`, `atl`, `tsb` (float)
  - `load` (int)
  - `dist` (float, km)
  - `time` (int, minutos)
  - `elev_gain`, `elev_loss` (int o `null`)
  - `calories` (int o `null`)
  - `effort` (float o `null`)
  - `race` (objeto o `null`)
- **Privacidad/tenancy**: sin payloads crudos ni credenciales; acceso limitado al coach/atleta dueño.

### Scale risks (no implementar ahora)
- Rango amplio + agregados por día puede crecer linealmente → considerar **paginación/limit** en futuro.
- Recompute en caliente en rangos grandes puede ser costoso → **cachear** o precalcular por día/semana.
- Precompute async (batch/cron) para rangos largos y evitar latencia en requests.
