import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AthleteLayout from '../components/AthleteLayout'
import PMCChart from '../components/PMCChart'
import { useAuth } from '../context/AuthContext'
import {
  getAthletePMC,
  getAthleteGoals,
  getAthleteWeeklySummary,
  getAthleteWellnessToday,
} from '../api/pmc'
import { getAthleteTrainingPhases } from '../api/periodization'

const RANGE_OPTIONS = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
]

const DAY_LABELS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

function readinessColors(score) {
  if (score >= 75) return { bg: 'bg-emerald-50', border: 'border-emerald-200', chip: 'bg-emerald-100 text-emerald-700', bar: 'bg-emerald-500' }
  if (score >= 50) return { bg: 'bg-amber-50', border: 'border-amber-200', chip: 'bg-amber-100 text-amber-700', bar: 'bg-amber-500' }
  if (score >= 25) return { bg: 'bg-orange-50', border: 'border-orange-200', chip: 'bg-orange-100 text-orange-700', bar: 'bg-orange-400' }
  return { bg: 'bg-red-50', border: 'border-red-200', chip: 'bg-red-100 text-red-700', bar: 'bg-red-400' }
}

function formatDistance(m) {
  if (!m) return '0 km'
  return `${(m / 1000).toFixed(1)} km`
}

function formatDuration(s) {
  if (!s) return '0 min'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m} min`
}

function priorityColor(priority) {
  if (priority === 'A') return 'bg-rose-100 text-rose-700'
  if (priority === 'B') return 'bg-amber-100 text-amber-700'
  return 'bg-slate-100 text-slate-600'
}

// ── PR-157: Periodization Timeline component ──────────────────────────────────

const PHASE_META = {
  carga:    { label: 'CARGA',    bg: 'bg-orange-100',  text: 'text-orange-700',  dot: 'bg-orange-500',  desc: 'Fase de construcción. Volumen alto, intensidad progresiva.' },
  descarga: { label: 'DESC',     bg: 'bg-green-100',   text: 'text-green-700',   dot: 'bg-green-500',   desc: 'Semana de recuperación. Reducí volumen 30-40%.' },
  carrera:  { label: 'CARRERA',  bg: 'bg-rose-100',    text: 'text-rose-700',    dot: 'bg-rose-500',    desc: 'Semana de competencia. Activaciones cortas, descansá.' },
  descanso: { label: 'DESCANSO', bg: 'bg-blue-100',    text: 'text-blue-700',    dot: 'bg-blue-500',    desc: 'Recuperación post-carrera. Actividad suave o descanso completo.' },
  lesion:   { label: 'LESIÓN',   bg: 'bg-slate-200',   text: 'text-slate-600',   dot: 'bg-slate-500',   desc: 'Recuperación de lesión. Seguí las indicaciones de tu coach.' },
}

function PeriodizationTimeline({ phases }) {
  const { phases: weeks, current_phase, current_phase_description } = phases
  if (!weeks || weeks.length === 0) return null

  const currentMeta = current_phase ? PHASE_META[current_phase] : null

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
      <h2 className="text-base font-semibold text-slate-900 mb-3">Tu Plan de Temporada</h2>

      {/* Scrollable horizontal timeline */}
      <div className="overflow-x-auto pb-1">
        <div className="flex gap-1.5 min-w-max">
          {weeks.map((w, i) => {
            const meta = w.phase ? PHASE_META[w.phase] : null
            const label = meta ? meta.label : '—'
            const isNow = w.is_current
            return (
              <div
                key={w.week_start}
                title={`Semana ${i + 1}: ${w.week_start}${meta ? ` — ${PHASE_META[w.phase].desc}` : ''}`}
                className={`flex flex-col items-center rounded-lg px-2 py-1.5 min-w-[52px] border transition-all ${
                  isNow
                    ? 'border-amber-400 ring-1 ring-amber-300 shadow-sm'
                    : 'border-transparent'
                } ${meta ? meta.bg : 'bg-slate-50'}`}
              >
                <span className={`text-xs font-bold leading-tight ${meta ? meta.text : 'text-slate-400'}`}>
                  {label}
                </span>
                <span className="text-[0.6rem] text-slate-400 mt-0.5">
                  {isNow ? 'HOY' : `Sem ${i + 1}`}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Current phase description */}
      {currentMeta && (
        <div className={`mt-3 flex items-start gap-2 rounded-lg p-3 ${currentMeta.bg}`}>
          <div className={`w-2.5 h-2.5 rounded-full mt-0.5 shrink-0 ${currentMeta.dot}`} />
          <div>
            <p className={`text-sm font-semibold ${currentMeta.text}`}>
              {currentMeta.label}
            </p>
            <p className="text-xs text-slate-600 mt-0.5">{current_phase_description}</p>
          </div>
        </div>
      )}

      {!current_phase && (
        <p className="text-xs text-slate-400 mt-2">Tu coach todavía no asignó fases para tu temporada.</p>
      )}
    </div>
  )
}

const AthleteProgress = () => {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [selectedDays, setSelectedDays] = useState(90)
  const [pmcData, setPmcData] = useState(null)
  const [goals, setGoals] = useState([])
  const [weekly, setWeekly] = useState(null)
  const [wellness, setWellness] = useState(null)
  const [phases, setPhases] = useState(null)
  const [loadingPMC, setLoadingPMC] = useState(true)
  const [loadingExtras, setLoadingExtras] = useState(true)

  useEffect(() => {
    const fetchPMC = async () => {
      setLoadingPMC(true)
      try {
        const res = await getAthletePMC(selectedDays)
        setPmcData(res.data)
      } catch {
        setPmcData(null)
      } finally {
        setLoadingPMC(false)
      }
    }
    fetchPMC()
  }, [selectedDays])

  useEffect(() => {
    const fetchExtras = async () => {
      setLoadingExtras(true)
      try {
        const [goalsRes, weeklyRes, wellnessRes, phasesRes] = await Promise.all([
          getAthleteGoals().catch(() => ({ data: { goals: [] } })),
          getAthleteWeeklySummary().catch(() => ({ data: null })),
          getAthleteWellnessToday().catch(() => ({ data: { submitted: false } })),
          getAthleteTrainingPhases(12).catch(() => ({ data: null })),
        ])
        setGoals(goalsRes.data?.goals ?? [])
        setWeekly(weeklyRes.data)
        setWellness(wellnessRes.data)
        setPhases(phasesRes.data)
      } finally {
        setLoadingExtras(false)
      }
    }
    fetchExtras()
  }, [])

  const current = pmcData?.current ?? {}
  const readinessScore = current.readiness_score ?? 0
  const readinessLabel = current.readiness_label ?? ''
  const readinessRec = current.readiness_recommendation ?? ''
  const colors = readinessColors(readinessScore)
  const hasData = pmcData?.days?.length > 0

  // Trend text for PMC chart
  const trendText = (() => {
    if (!hasData) return null
    const d = pmcData.days
    const startCtl = Math.round(d[0]?.ctl ?? 0)
    const endCtl = Math.round(current.ctl ?? 0)
    const delta = endCtl - startCtl
    if (delta > 0) return `En los últimos ${selectedDays} días tu fitness subió de ${startCtl} a ${endCtl} ↗`
    if (delta < 0) return `En los últimos ${selectedDays} días tu fitness bajó de ${startCtl} a ${endCtl} ↘`
    return `Tu fitness se mantuvo estable en ${endCtl} en los últimos ${selectedDays} días`
  })()

  return (
    <AthleteLayout user={user}>
      <div className="p-6 space-y-6 max-w-2xl mx-auto">

        {/* HEADER */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900">Mi Progreso</h1>
        </div>

        {/* SECTION 1: READINESS HERO */}
        {loadingPMC ? (
          <div className={`rounded-2xl border p-8 animate-pulse bg-slate-50 border-slate-200 text-center`}>
            <div className="h-8 w-24 bg-slate-200 rounded mx-auto mb-3" />
            <div className="h-16 w-32 bg-slate-200 rounded mx-auto mb-3" />
            <div className="h-2 w-48 bg-slate-200 rounded mx-auto mb-3" />
            <div className="h-5 w-28 bg-slate-200 rounded mx-auto" />
          </div>
        ) : (
          <div className={`rounded-2xl border p-8 text-center ${colors.bg} ${colors.border}`}>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">¿CÓMO ESTÁS HOY?</p>
            <p className="text-6xl font-bold text-slate-800 mb-3">{readinessScore}<span className="text-2xl text-slate-400 font-normal"> / 100</span></p>
            <div className="w-64 mx-auto mb-3">
              <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                <div className={`h-2 rounded-full transition-all duration-500 ${colors.bar}`} style={{ width: `${readinessScore}%` }} />
              </div>
            </div>
            {readinessLabel && (
              <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold mb-2 ${colors.chip}`}>
                {readinessLabel}
              </span>
            )}
            {readinessRec && (
              <p className="text-sm text-slate-600 mt-1">{readinessRec}</p>
            )}
            {!hasData && !loadingPMC && (
              <p className="text-xs text-slate-400 mt-2">Conectá tu dispositivo para mejorar la precisión</p>
            )}
          </div>
        )}

        {/* SECTION 2: GOALS COUNTDOWN */}
        {!loadingExtras && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <h2 className="text-base font-semibold text-slate-900 mb-3">Tus Objetivos</h2>
            {goals.length === 0 ? (
              <div className="text-center py-4">
                <p className="text-sm text-slate-500 mb-2">Todavía no cargaste tu próxima carrera.</p>
                <button
                  onClick={() => navigate('/athlete/profile')}
                  className="text-sm text-amber-600 font-medium hover:underline"
                >
                  Agregá tu objetivo en tu Perfil →
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {goals.map(goal => {
                  const urgent = goal.days_remaining >= 0 && goal.days_remaining <= 7
                  const past = goal.days_remaining < 0
                  return (
                    <div key={goal.id} className={`rounded-xl border p-4 ${urgent ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-slate-50'}`}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-800 leading-tight">{goal.name}</p>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full shrink-0 ${priorityColor(goal.priority)}`}>
                          {goal.priority}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">{goal.date}</p>
                      <p className={`text-xl font-bold mt-2 ${past ? 'text-slate-400' : urgent ? 'text-rose-600' : 'text-amber-600'}`}>
                        {past
                          ? 'Ya pasó'
                          : goal.days_remaining === 0
                          ? '¡Hoy es el día!'
                          : goal.days_remaining <= 7
                          ? `¡En ${goal.days_remaining} días!`
                          : `En ${goal.days_remaining} días`}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* SECTION 3: PERIODIZATION TIMELINE — PR-157 */}
        {!loadingExtras && phases && phases.phases && phases.phases.some(p => p.phase) && (
          <PeriodizationTimeline phases={phases} />
        )}

        {/* SECTION 4: WEEKLY SUMMARY */}
        {!loadingExtras && weekly && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <h2 className="text-base font-semibold text-slate-900 mb-4">Esta Semana</h2>
            <div className="flex justify-center gap-2 mb-4">
              {weekly.days.map((day, i) => (
                <div key={day.date} className="flex flex-col items-center gap-1">
                  <span className="text-xs text-slate-400">{DAY_LABELS[i]}</span>
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium ${
                    day.completed ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-400'
                  }`}>
                    {day.completed ? '✓' : '·'}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-sm text-center text-slate-600 mb-1">
              <span className="font-semibold">{weekly.completed_sessions}/{weekly.planned_sessions}</span> sesiones
              {weekly.total_distance_m > 0 && <> · <span className="font-semibold">{formatDistance(weekly.total_distance_m)}</span></>}
              {weekly.total_duration_s > 0 && <> · <span className="font-semibold">{formatDuration(weekly.total_duration_s)}</span></>}
              {weekly.total_elevation_m > 0 && <> · <span className="font-semibold">{weekly.total_elevation_m.toLocaleString()} m↑</span></>}
            </p>
            {weekly.streak_days > 0 && (
              <p className="text-sm text-center text-amber-600 font-medium mt-1">
                🔥 {weekly.streak_days} días consecutivos
              </p>
            )}
          </div>
        )}

        {/* SECTION 5: SIMPLIFIED PMC CHART */}
        {!loadingPMC && hasData && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-base font-semibold text-slate-900">Tu Evolución</h2>
              <div className="flex gap-1.5">
                {RANGE_OPTIONS.map(({ label, days }) => (
                  <button
                    key={label}
                    onClick={() => setSelectedDays(days)}
                    className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                      selectedDays === days
                        ? 'bg-amber-500 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {trendText && (
              <p className="text-xs text-slate-500 mb-3">{trendText}</p>
            )}
            <PMCChart
              days={pmcData.days}
              height={260}
              humanLabels={true}
            />
          </div>
        )}

        {/* SECTION 6: WELLNESS CHECK-IN PROMPT */}
        {!loadingExtras && wellness && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            {wellness.submitted ? (
              <div>
                <h2 className="text-base font-semibold text-slate-900 mb-3">Check-in de Hoy</h2>
                <div className="flex flex-wrap gap-2 justify-center">
                  <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-sm">😴 Sueño: {wellness.sleep_quality}/5</span>
                  <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-sm">😊 Ánimo: {wellness.mood}/5</span>
                  <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-sm">⚡ Energía: {wellness.energy}/5</span>
                  <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-sm">💪 Dolor: {wellness.muscle_soreness}/5</span>
                  <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-sm">😰 Estrés: {wellness.stress}/5</span>
                </div>
              </div>
            ) : (
              <div className="text-center py-2">
                <h2 className="text-base font-semibold text-slate-900 mb-1">¿Cómo te sentís hoy?</h2>
                <p className="text-sm text-slate-500 mb-3">
                  Completá tu check-in diario para mejorar tu Readiness Score
                </p>
                <button
                  onClick={() => navigate('/athlete/profile')}
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  Completar Check-in
                </button>
              </div>
            )}
          </div>
        )}

      </div>
    </AthleteLayout>
  )
}

export default AthleteProgress
