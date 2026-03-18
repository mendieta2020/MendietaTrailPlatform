# TrainingPeaks Workout Builder — Competitor Analysis
> **Phase:** P2 — Historical Data, Analytics & Billing
> **Purpose:** Identify feature gaps and define the roadmap to match and surpass TrainingPeaks' structured workout builder.
> **Date:** 2026-03-18

---

## 1. TrainingPeaks Workout Builder — Data Structure

### 1.1 Top-Level Workout Fields

| Field | TrainingPeaks | Quantoryn (`PlannedWorkout`) | Gap |
|-------|--------------|------------------------------|-----|
| Name | ✅ | ✅ `name` | None |
| Description | ✅ | ✅ `description` | None |
| Sport / Discipline | ✅ (run, bike, swim, MTB, triathlon…) | ✅ `discipline` | Minor: Quantoryn missing swim, MTB, triathlon |
| Session type | ✅ (workout category) | ✅ `session_type` | None |
| Estimated duration | ✅ (seconds) | ✅ `estimated_duration_seconds` | None |
| Estimated distance | ✅ (meters) | ✅ `estimated_distance_meters` | None |
| **TSS (Training Stress Score)** | ✅ computed from IF × duration | ❌ Missing | **High-value gap** |
| **IF (Intensity Factor = NP/FTP)** | ✅ computed | ❌ Missing | **High-value gap** |
| **TSB / ATL / CTL preview** | ✅ shows impact on form chart | ❌ Missing | **P2 analytics gap** |
| Tags / Labels | ✅ | ❌ Missing | Medium |
| Attachments / Files | ✅ (GPX, MRC, ZWO, ERG) | ❌ Missing | Low for P2 |
| Visibility (public/private) | ✅ | ✅ `WorkoutLibrary.is_public` | None |
| Coach notes | ✅ | ✅ `description` | Minor: one field vs two |

### 1.2 Step / Interval Fields (per step inside a block)

| Field | TrainingPeaks | Quantoryn (`WorkoutInterval`) | Gap |
|-------|--------------|-------------------------------|-----|
| Step name / description | ✅ | ✅ `description` | None |
| Duration (seconds) | ✅ | ✅ `duration_seconds` | None |
| Distance (meters) | ✅ | ✅ `distance_meters` | None |
| Metric type (HR / Pace / Power / RPE / Free) | ✅ | ✅ `metric_type` | None |
| Target value — single | ✅ | ✅ `target_label` | Minor: TP stores as numeric |
| **Target range (low–high)** | ✅ (e.g., 140–155 bpm) | ✅ `target_value_low` / `target_value_high` | Already modeled — not exposed in UI |
| Recovery duration | ✅ | ✅ `recovery_seconds` | None |
| Recovery distance | ✅ | ✅ `recovery_distance_meters` | Already modeled — not exposed in UI |
| **Repetitions (repeat count)** | ✅ (e.g., 6× 400m) | ❌ No field in model or serializer | **Critical gap** |
| **Cadence target** | ✅ (rpm for cycling) | ❌ Missing | Medium |
| **Power targets (%FTP / watts)** | ✅ (both relative and absolute) | ⚠️ `target_label` stores as string | Medium: needs structured numeric fields |
| **Pace targets (%threshold / min/km)** | ✅ | ⚠️ `target_label` stores as string | Medium |
| **HR Zone targets** | ✅ (Z1–Z5) | ⚠️ `target_label` stores as string | Medium |
| Video / media link | ✅ | ✅ `video_url` | None |
| Step type (warmup / active / cooldown / rest / repeat-open / repeat-closed) | ✅ | ⚠️ Partial via `WorkoutBlock.block_type` | Medium |

### 1.3 Block / Segment Structure

| Feature | TrainingPeaks | Quantoryn (`WorkoutBlock`) | Gap |
|---------|--------------|---------------------------|-----|
| Ordered segments | ✅ | ✅ `order_index` | None |
| Block type labels | ✅ | ✅ `block_type` | None |
| **Nested repeats (repeat block containing steps)** | ✅ (e.g., 5× [400m hard + 90s rest]) | ❌ No recursive block structure | **Critical gap** |
| Block description | ✅ | ✅ `description` | None |

---

## 2. TrainingPeaks Unique Features (not yet in Quantoryn)

### 2.1 Auto-Calculated Training Load Metrics
TrainingPeaks computes **TSS, IF, NP (Normalized Power)** and **ATL/CTL/TSB** projections at the time of workout creation. The coach sees exactly how the planned workout will affect the athlete's form curve *before* assigning it.

- **TSS** = (duration_sec × NP × IF) / (FTP × 3600) × 100
- **IF** = NP / FTP (or pace_equivalent / threshold_pace for running)

**Quantoryn gap:** We have `PlannedWorkout` but no TSS/IF stored or computed. The analytics models (`PMCHistory`, `HistorialFitness`) exist for *actual* completed data, not planned projections.

### 2.2 Structured File Export
TrainingPeaks exports workouts as:
- `.MRC` (power-based, CompuTrainer / Zwift)
- `.ZWO` (Zwift native)
- `.ERG` (generic power file)
- `.FIT` structured workout (Garmin, COROS, Wahoo device sync)

**Quantoryn gap:** No export capability. This is a high-value provider-side feature.

### 2.3 Device Sync
Workouts sync directly to Garmin Connect, Wahoo ELEMNT, COROS, Polar Flow, and Suunto app. Athletes see the structured workout on their device without manual entry.

**Quantoryn gap:** We have provider integrations (strava, garmin, coros, suunto, polar, wahoo) but no outbound workout delivery that pushes structured workout files to devices.

### 2.4 Workout Visualization
TrainingPeaks renders a **graphical step chart** (power/pace/HR profile) at design time. Coaches see the intensity profile before publishing.

**Quantoryn gap:** WorkoutBuilder is text/form-based. No visual intensity profile.

### 2.5 Zones Configuration
TrainingPeaks stores per-athlete **FTP, threshold pace, LTHR** and uses them to resolve relative targets (e.g., "85% FTP" → "261W for this athlete"). Targets adapt per athlete.

**Quantoryn gap:** No per-athlete zone configuration exists yet. `target_value_low/high` are absolute, not relative.

### 2.6 Compliance Scoring per Step
TrainingPeaks shows step-level compliance after execution: "you hit 4/6 intervals at target power." Each interval is matched to the actual workout stream.

**Quantoryn gap:** `WorkoutReconciliation` exists but scores at workout level. No step-level compliance scoring.

---

## 3. Feature Comparison Score

| Category | TrainingPeaks | Quantoryn (current) |
|----------|:---:|:---:|
| Workout structure (blocks/steps) | 5/5 | 4/5 |
| Intensity targets | 5/5 | 3/5 |
| Repetitions / nested repeats | 5/5 | 1/5 |
| Training load (TSS/IF) | 5/5 | 0/5 |
| Zone-relative targets | 5/5 | 1/5 |
| Device / provider sync | 5/5 | 1/5 |
| Compliance scoring | 5/5 | 2/5 |
| Visual workout profile | 4/5 | 0/5 |
| **Overall** | **39/40** | **12/40** |

---

## 4. Proposed Schema Changes for P2

### 4.1 Priority: CRITICAL (blocks workout usability)

#### 4.1.1 Add `repetitions` to `WorkoutInterval`

```python
# core/models.py — WorkoutInterval
repetitions = models.PositiveSmallIntegerField(
    default=1,
    help_text="Number of times this interval is repeated. 1 = no repeat.",
)
```

**Why:** TP's most-used feature is "6×400m @ threshold." Without `repetitions`, coaches must manually create 6 identical interval rows. This destroys the UX.

**Migration:** `default=1` → safe, non-breaking.

#### 4.1.2 Expose `target_value_low` / `target_value_high` in UI

These fields already exist in the model and serializer but the WorkoutBuilder UI only exposes `target_label` (string). The fix is pure frontend — add low/high numeric fields alongside `target_label`.

---

### 4.2 Priority: HIGH (training load — Quantoryn's scientific differentiator)

#### 4.2.1 Add `planned_tss` and `planned_if` to `PlannedWorkout`

```python
# core/models.py — PlannedWorkout
planned_tss = models.FloatField(
    null=True, blank=True,
    help_text="Coach-estimated Training Stress Score for this session.",
)
planned_if = models.FloatField(
    null=True, blank=True,
    help_text="Coach-estimated Intensity Factor (0.0–1.2).",
)
```

These can be auto-computed in a service function using:
- `estimated_duration_seconds` + `planned_if` → `planned_tss`
- Or set manually by the coach.

**Why:** This enables the PMC (Performance Management Chart) to project *planned* CTL/ATL/TSB curves, not just actual ones. This is the core coach planning loop.

#### 4.2.2 Add `AthleteZones` model

```python
class AthleteZones(models.Model):
    """Per-athlete, per-discipline zone configuration."""
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    athlete = models.ForeignKey("Athlete", on_delete=models.CASCADE)
    discipline = models.CharField(max_length=20, choices=PlannedWorkout.Discipline.choices)
    ftp_watts = models.PositiveIntegerField(null=True, blank=True)
    threshold_pace_sec_km = models.PositiveIntegerField(null=True, blank=True)
    lthr_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    vo2max_pace_sec_km = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ("organization", "athlete", "discipline")
```

**Why:** Without athlete zones, TSS/IF computation and zone-relative targets are impossible. This is a P2 foundational model.

---

### 4.3 Priority: MEDIUM (enhances coach UX)

#### 4.3.1 Add `cadence_rpm_low` / `cadence_rpm_high` to `WorkoutInterval`

```python
cadence_rpm_low = models.PositiveSmallIntegerField(null=True, blank=True)
cadence_rpm_high = models.PositiveSmallIntegerField(null=True, blank=True)
```

Relevant for cycling blocks. Migration-safe (nullable).

#### 4.3.2 Add `tags` to `PlannedWorkout`

```python
# Using django-taggit or a simple ArrayField (Postgres)
tags = ArrayField(models.CharField(max_length=50), blank=True, default=list)
```

Enables library filtering: "show me all threshold bike sessions."

#### 4.3.3 Add `target_value_unit` to `WorkoutInterval`

```python
target_value_unit = models.CharField(
    max_length=20,
    blank=True, default="",
    choices=[("watts", "Watts"), ("pct_ftp", "% FTP"), ("bpm", "BPM"), ("pct_lthr", "% LTHR"),
             ("min_km", "min/km"), ("pct_threshold_pace", "% Threshold Pace"), ("rpe", "RPE 1–10")],
    help_text="Unit for target_value_low / target_value_high.",
)
```

**Why:** Makes targets machine-interpretable for TSS computation and device export.

---

### 4.4 Priority: LOW (P2 later / P3)

- Nested repeat blocks (requires recursive `parent_block` FK or denormalized repeat structure)
- Structured file export (`.FIT`, `.ZWO`) — requires provider-side implementation
- Outbound workout delivery to devices (already stubbed in `integrations/outbound/`)
- Step-level compliance scoring (depends on ActivityStream granularity)
- Workout visualization (frontend chart — pure frontend feature)

---

## 5. Recommended P2 PRs (Prioritized)

| PR | Description | LOC est. | Risk |
|----|-------------|----------|------|
| PR-141 | Add `repetitions` to `WorkoutInterval` + expose in WorkoutBuilder UI | ~80 | Low |
| PR-142 | Expose `target_value_low/high` + `target_value_unit` in WorkoutBuilder UI | ~100 | Low |
| PR-143 | `AthleteZones` model + CRUD API | ~200 | Medium |
| PR-144 | `planned_tss` / `planned_if` on `PlannedWorkout` + auto-compute service | ~150 | Medium |
| PR-145 | PMC chart uses planned TSS for projected CTL/ATL/TSB curves | ~200 | Medium |

---

## 6. Where Quantoryn Can Surpass TrainingPeaks

TrainingPeaks is strong on structure but has known weaknesses:

1. **Vertical discipline focus** — built for triathlon/cycling. Trail running and mountain sports are second-class citizens. Quantoryn targets trail running as the primary discipline.

2. **No scientific prescription framework** — TP prescribes workouts but has no built-in periodization model or RPE-based science model. Quantoryn can embed the science (Seiler's polarized model, RPE-based load monitoring, strain/stress models).

3. **Athlete-coach collaboration is read-only** — TP athletes can view and log, but two-way feedback loops (athlete notes → coach adjusts plan) are weak. Quantoryn has `WorkoutReconciliation` and `AthleteGoal` as foundations for bidirectional loops.

4. **No terrain / elevation targets** — critical for trail running. TP has no native D+ (elevation gain) target per step. Quantoryn's `primary_target_variable` already includes `elevation_gain`.

5. **No multi-sport team analytics** — TP is athlete-centric. Quantoryn's org/team model enables coach-level fleet analytics: "show me all athletes who are under-recovered this week."

---

*Analysis by Antigravity Agent · 2026-03-18*
