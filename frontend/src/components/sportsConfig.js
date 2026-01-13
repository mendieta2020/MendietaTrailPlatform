export const SPORT_LABELS = {
  TRAIL: 'Trail',
  RUN: 'Running',
  BIKE: 'Ciclismo',
  WALK: 'Caminata',
  STRENGTH: 'Strength / Functional',
  FUNCTIONAL: 'Strength / Functional',
  WORKOUT: 'Strength / Functional',
  OTHER: 'Strength / Functional',
};

export const DISTANCE_SPORTS = new Set(['RUN', 'TRAIL', 'BIKE', 'WALK']);

export function getSportLabel(code) {
  return SPORT_LABELS[code] ?? code;
}

export function isDistanceSport(code) {
  return DISTANCE_SPORTS.has(code);
}

export function splitPerSportTotals(perSportTotals = {}) {
  const entries = Object.values(perSportTotals);
  return entries.reduce(
    (acc, sport) => {
      if (isDistanceSport(sport.code)) {
        acc.distanceTotals.push(sport);
      } else {
        acc.nonDistanceTotals.push(sport);
      }
      return acc;
    },
    { distanceTotals: [], nonDistanceTotals: [] },
  );
}
