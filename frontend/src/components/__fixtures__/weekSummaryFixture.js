const weekSummaryFixture = {
  athlete_id: 7,
  week: '2026-W03',
  start_date: '2026-01-12',
  end_date: '2026-01-18',
  total_distance_km: 14.01,
  total_duration_minutes: 80,
  total_elevation_gain_m: 92,
  total_elevation_loss_m: 155,
  total_elevation_total_m: 247,
  total_calories_kcal: 866,
  sessions_count: 1,
  sessions_by_type: { RUN: 1 },
  totals_by_type: { RUN: { distance_km: 14.01 } },
  per_sport_totals: {
    TRAIL: {
      duration_minutes: 615,
      duration_s: 36900,
      calories_kcal: 6996,
      load: 1460.3,
      distance_km: 112.08,
      elevation_gain_m: 2797,
      elevation_loss_m: 3110,
      elevation_total_m: 5907,
    },
    STRENGTH: {
      duration_minutes: 45,
      duration_s: 2700,
      calories_kcal: 300,
      load: 120,
    },
    OTHER: {
      duration_minutes: 90,
      duration_s: 5400,
      calories_kcal: 600,
      load: 280,
    },
  },
  compliance: {},
  alerts: [],
};

export default weekSummaryFixture;
