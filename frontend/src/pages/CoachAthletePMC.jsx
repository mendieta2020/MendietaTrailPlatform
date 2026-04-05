import React, { useState, useReducer, useEffect, useRef } from 'react'
import {
  Alert, MenuItem, Select, Skeleton, Tooltip,
  Tabs, Tab, Box, Typography, TextField, Button, CircularProgress,
} from '@mui/material'
import { ChevronLeft, TrendingUp, Zap, Activity, Heart, Smile, Dumbbell } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../components/Layout'
import PMCChart from '../components/PMCChart'
import { VolumeBarChart, ComplianceBarChart } from '../components/VolumeChart'
import WellnessHeatmap from '../components/WellnessHeatmap'
import ShareReportModal from '../components/ShareReportModal'
import AthleteProfileTab from '../components/AthleteProfileTab'
import AthleteInjuriesTab from '../components/AthleteInjuriesTab'
import AthleteGoalsTab from '../components/AthleteGoalsTab'
import AthleteWellnessTab from '../components/AthleteWellnessTab'
import {
  getCoachAthletePMC,
  getTrainingVolume,
  getAthleteWellness,
  getAthleteCompliance,
  getCoachAthleteNotes,
  updateCoachAthleteNotes,
} from '../api/pmc'

// ─── fetch reducer ───────────────────────────────────────────────────────────
function fetchReducer(state, action) {
  switch (action.type) {
    case 'FETCH': return { loading: true, error: null, data: state.data }
    case 'OK':    return { loading: false, error: null, data: action.data }
    case 'ERR':   return { loading: false, error: action.error, data: null }
    case 'CLEAR': return { ...state, error: null }
    default:      return state
  }
}
const IDLE = { loading: false, error: null, data: null }

// ─── constants ────────────────────────────────────────────────────────────────
const RANGE_OPTIONS = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
]

const METRIC_OPTIONS = [
  { value: 'pmc',      label: 'Rendimiento (PMC)' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'wellness', label: 'Bienestar' },
  { value: 'vol-run',  label: 'Volumen Trail/Running' },
  { value: 'vol-hours', label: 'Volumen (Horas + Calorías)' },
  { value: 'vol-cycling', label: 'Volumen Ciclismo' },
  { value: 'effort',   label: 'Esfuerzo (Carga TSS)' },
  { value: 'strength', label: 'Fuerza (Carga)' },
  { value: 'zones',    label: 'Tiempo en Zonas' },
]

const VOLUME_METRICS_WITH_PRECISION = new Set([
  'compliance', 'vol-run', 'vol-hours', 'vol-cycling', 'effort', 'strength',
])

const CARD_TOOLTIPS = {
  readiness: 'Índice de disposición 0-100. Combina carga de entrenamiento y bienestar. >75 = listo para entrenar fuerte.',
  ctl:       'Fitness acumulado en 42 días. Mayor número = más preparado. Se construye con entrenamiento consistente.',
  atl:       'Fatiga de los últimos 7 días. Número alto = mucha carga reciente. Necesita descanso para bajar.',
  tsb:       'Balance fitness menos fatiga. Positivo = fresco para competir. Negativo = en fase de construcción.',
  acwr:      'Ratio carga aguda/crónica. 0.8-1.3 = zona segura. >1.5 = riesgo de lesión duplicado.',
  compliance:'Porcentaje de cumplimiento del plan semanal. 100% = hiciste todo lo planificado.',
  wellness:  'Promedio de check-ins: fatiga, dolor, sueño, estrés, ánimo. Escala 1-5.',
}

// ─── helpers ──────────────────────────────────────────────────────────────────
function readinessColor(score) {
  if (score >= 75) return { text: 'text-green-500', border: 'border-l-green-500' }
  if (score >= 50) return { text: 'text-amber-500', border: 'border-l-amber-500' }
  return { text: 'text-red-500', border: 'border-l-red-500' }
}

function tsbColor(tsb) {
  return tsb >= 0 ? 'text-emerald-500' : 'text-red-500'
}

function acwrRisk(acwr) {
  if (acwr > 1.5) return { label: 'Alto riesgo', color: 'bg-red-100 text-red-700' }
  if (acwr > 1.3) return { label: 'Precaución', color: 'bg-amber-100 text-amber-700' }
  if (acwr >= 0.8) return { label: 'Zona segura', color: 'bg-green-100 text-green-700' }
  return { label: 'Carga baja', color: 'bg-slate-100 text-slate-600' }
}

// ─── sub-components ───────────────────────────────────────────────────────────
const LoadingSkeleton = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {[...Array(7)].map((_, i) => (
        <Skeleton key={i} variant="rectangular" height={120} className="rounded-xl" />
      ))}
    </div>
    <Skeleton variant="rectangular" height={380} className="rounded-xl" />
  </div>
)

const EmptyState = ({ message }) => (
  <div className="flex flex-col items-center justify-center py-16 text-center">
    <p className="text-slate-500 text-sm">{message}</p>
  </div>
)

// ─── Coach notes (always visible at bottom) ───────────────────────────────────
function CoachNotes({ membershipId }) {
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const debounceRef = useRef(null)

  useEffect(() => {
    if (!membershipId) return
    getCoachAthleteNotes(membershipId)
      .then(res => { setNotes(res.data.coach_notes ?? ''); setLoading(false) })
      .catch(() => setLoading(false))
  }, [membershipId])

  const handleChange = (val) => {
    setNotes(val)
    setSaved(false)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      save(val)
    }, 3000)
  }

  const save = async (val) => {
    setSaving(true)
    try {
      await updateCoachAthleteNotes(membershipId, val)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* save failed silently */ }
    finally { setSaving(false) }
  }

  if (loading) return null

  return (
    <div className="mt-6 bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Notas del coach</p>
        {saving && <span className="text-xs text-slate-400">Guardando...</span>}
        {saved && !saving && <span className="text-xs text-emerald-500">Guardado</span>}
      </div>
      <textarea
        value={notes}
        onChange={e => handleChange(e.target.value)}
        placeholder="Notas privadas sobre este atleta..."
        rows={3}
        className="w-full text-sm text-slate-700 border border-slate-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
      />
      <button
        onClick={() => save(notes)}
        disabled={saving}
        className="mt-2 px-4 py-1.5 text-xs font-semibold rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
      >
        Guardar nota
      </button>
    </div>
  )
}

// ─── main component ───────────────────────────────────────────────────────────
const CoachAthletePMC = () => {
  const navigate = useNavigate()
  const { membershipId } = useParams()

  // Active tab: 0=Rendimiento, 1=Perfil, 2=Lesiones, 3=Objetivos, 4=Wellness
  const [activeTab, setActiveTab] = useState(0)

  const [selectedDays, setSelectedDays]     = useState(90)
  const [selectedMetric, setSelectedMetric] = useState('pmc')
  const [precision, setPrecision]           = useState('weekly')

  const [pmcState,       dispatchPMC]       = useReducer(fetchReducer, { loading: true, error: null, data: null })
  const [volumeState,    dispatchVolume]    = useReducer(fetchReducer, IDLE)
  const [wellnessState,  dispatchWellness]  = useReducer(fetchReducer, IDLE)
  const [complianceState,dispatchCompliance]= useReducer(fetchReducer, IDLE)
  const [shareOpen,      setShareOpen]      = useState(false)

  // PMC always loads on mount + when days change
  useEffect(() => {
    dispatchPMC({ type: 'FETCH' })
    getCoachAthletePMC(membershipId, selectedDays)
      .then(res => dispatchPMC({ type: 'OK', data: res.data }))
      .catch(() => dispatchPMC({ type: 'ERR', error: 'No se pudieron cargar los datos del atleta.' }))
  }, [membershipId, selectedDays])

  // Load chart data when metric changes
  useEffect(() => {
    if (selectedMetric === 'pmc') return

    if (selectedMetric === 'wellness') {
      dispatchWellness({ type: 'FETCH' })
      getAthleteWellness(membershipId, selectedDays)
        .then(res => dispatchWellness({ type: 'OK', data: res.data }))
        .catch(() => dispatchWellness({ type: 'ERR', error: 'No se pudieron cargar los datos de bienestar.' }))
      return
    }

    if (selectedMetric === 'compliance') {
      dispatchCompliance({ type: 'FETCH' })
      getAthleteCompliance(membershipId, { days: selectedDays, precision })
        .then(res => dispatchCompliance({ type: 'OK', data: res.data }))
        .catch(() => dispatchCompliance({ type: 'ERR', error: 'No se pudieron cargar los datos de compliance.' }))
      return
    }

    const metricMap = {
      'vol-run':   { metric: 'distance', sport: 'run' },
      'vol-hours': { metric: 'duration', sport: 'all' },
      'vol-cycling': { metric: 'distance', sport: 'cycling' },
      'effort':    { metric: 'load', sport: 'all' },
      'strength':  { metric: 'load', sport: 'strength' },
    }
    const params = metricMap[selectedMetric]
    if (params) {
      dispatchVolume({ type: 'FETCH' })
      getTrainingVolume(membershipId, { ...params, precision, days: selectedDays })
        .then(res => dispatchVolume({ type: 'OK', data: res.data }))
        .catch(() => dispatchVolume({ type: 'ERR', error: 'No se pudieron cargar los datos de volumen.' }))
    }
  }, [membershipId, selectedMetric, selectedDays, precision])

  const pmcData     = pmcState.data
  const current     = pmcData?.current ?? {}
  const athleteName = pmcData?.athlete_name ?? 'Atleta'
  const hasPMC      = pmcData?.days?.length > 0

  const ctl  = current.ctl  ?? 0
  const atl  = current.atl  ?? 0
  const tsb  = current.tsb  ?? 0
  const acwr = ctl > 0 ? +(atl / ctl).toFixed(2) : null
  const readinessScore = current.readiness_score ?? 0
  const readinessLabel = current.readiness_label ?? '—'
  const rcol = readinessColor(readinessScore)
  const tsbDisplay = tsb >= 0 ? `+${Math.round(tsb)}` : `${Math.round(tsb)}`
  const acwrRiskInfo = acwr !== null ? acwrRisk(acwr) : null

  const wellnessAvg = wellnessState.data?.period_average
  const showPrecision = VOLUME_METRICS_WITH_PRECISION.has(selectedMetric)

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <Layout>
      <div className="p-6 space-y-4">

        {/* BACK BUTTON */}
        <button
          onClick={() => navigate('/coach/analytics')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Volver al equipo
        </button>

        {/* HEADER */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{athleteName}</h1>
            <p className="text-sm text-slate-500">Vista de atleta — análisis completo</p>
          </div>
          <button
            onClick={() => setShareOpen(true)}
            className="px-3 py-1.5 text-sm rounded-lg font-medium bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors self-start"
          >
            Compartir Reporte
          </button>
        </div>

        {/* TABS */}
        <Box sx={{ borderBottom: '1px solid #e2e8f0' }}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            sx={{
              '& .MuiTab-root': { fontSize: '0.85rem', fontWeight: 500, minWidth: 100, textTransform: 'none' },
              '& .Mui-selected': { color: '#00D4AA', fontWeight: 700 },
              '& .MuiTabs-indicator': { bgcolor: '#00D4AA' },
            }}
          >
            <Tab label="Rendimiento" />
            <Tab label="Perfil" />
            <Tab label="Lesiones" />
            <Tab label="Objetivos" />
            <Tab label="Wellness" />
          </Tabs>
        </Box>

        {/* ── TAB: Rendimiento ── */}
        {activeTab === 0 && (
          <>
            {/* Range selector */}
            <div className="flex flex-wrap items-center gap-2">
              {RANGE_OPTIONS.map(({ label, days }) => (
                <button
                  key={label}
                  onClick={() => setSelectedDays(days)}
                  className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                    selectedDays === days
                      ? 'bg-amber-500 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* TOP ERROR */}
            {pmcState.error && (
              <Alert severity="error" onClose={() => dispatchPMC({ type: 'CLEAR' })}>
                {pmcState.error}
              </Alert>
            )}

            {pmcState.loading ? <LoadingSkeleton /> : (
              <>
                {/* 6 KPI CARDS */}
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  <Tooltip title={CARD_TOOLTIPS.readiness} placement="top" arrow>
                    <div className={`bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 ${rcol.border} p-5 cursor-help`}>
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">Readiness</p>
                        <Heart className="w-4 h-4 text-rose-400" />
                      </div>
                      <p className={`text-4xl font-bold ${rcol.text} leading-none`}>{readinessScore}</p>
                      <p className="text-xs text-slate-500 mt-2">{readinessLabel}</p>
                    </div>
                  </Tooltip>

                  <Tooltip title={CARD_TOOLTIPS.ctl} placement="top" arrow>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-blue-500 p-5 cursor-help">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">CTL — Forma</p>
                        <TrendingUp className="w-4 h-4 text-blue-400" />
                      </div>
                      <p className="text-4xl font-bold text-blue-500 leading-none">{Math.round(ctl)}</p>
                      <p className="text-xs text-slate-500 mt-2">Fitness acumulado (42d)</p>
                    </div>
                  </Tooltip>

                  <Tooltip title={CARD_TOOLTIPS.atl} placement="top" arrow>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-orange-500 p-5 cursor-help">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">ATL — Fatiga</p>
                        <Zap className="w-4 h-4 text-orange-400" />
                      </div>
                      <p className="text-4xl font-bold text-orange-500 leading-none">{Math.round(atl)}</p>
                      <p className="text-xs text-slate-500 mt-2">Carga reciente (7d)</p>
                    </div>
                  </Tooltip>

                  <Tooltip title={CARD_TOOLTIPS.tsb} placement="top" arrow>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-emerald-500 p-5 cursor-help">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">TSB — Balance</p>
                        <Activity className="w-4 h-4 text-emerald-400" />
                      </div>
                      <p className={`text-4xl font-bold ${tsbColor(tsb)} leading-none`}>{tsbDisplay}</p>
                      <p className="text-xs text-slate-500 mt-2">Forma / Frescura</p>
                    </div>
                  </Tooltip>

                  <Tooltip title={CARD_TOOLTIPS.acwr} placement="top" arrow>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-purple-500 p-5 cursor-help">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">ACWR</p>
                        <TrendingUp className="w-4 h-4 text-purple-400" />
                      </div>
                      <p className="text-4xl font-bold text-purple-500 leading-none">
                        {acwr !== null ? acwr.toFixed(2) : '—'}
                      </p>
                      {acwrRiskInfo && (
                        <span className={`inline-block text-[10px] font-medium px-2 py-0.5 rounded-full mt-2 ${acwrRiskInfo.color}`}>
                          {acwrRiskInfo.label}
                        </span>
                      )}
                    </div>
                  </Tooltip>

                  <Tooltip title={CARD_TOOLTIPS.wellness} placement="top" arrow>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-pink-500 p-5 cursor-help">
                      <div className="flex items-start justify-between mb-1">
                        <p className="text-xs uppercase tracking-wide text-slate-500">Bienestar</p>
                        <Smile className="w-4 h-4 text-pink-400" />
                      </div>
                      <p className="text-4xl font-bold text-pink-500 leading-none">
                        {wellnessAvg != null ? wellnessAvg.toFixed(1) : '—'}
                      </p>
                      <p className="text-xs text-slate-500 mt-2">Promedio check-ins /5</p>
                    </div>
                  </Tooltip>
                </div>

                {/* FILTER BAR */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-slate-600">Métrica</label>
                    <Select
                      value={selectedMetric}
                      onChange={e => setSelectedMetric(e.target.value)}
                      size="small"
                      sx={{ fontSize: 13, minWidth: 220 }}
                    >
                      {METRIC_OPTIONS.map(opt => (
                        <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: 13 }}>
                          {opt.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </div>
                  {showPrecision && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs font-medium text-slate-600">Precisión</label>
                      <Select
                        value={precision}
                        onChange={e => setPrecision(e.target.value)}
                        size="small"
                        sx={{ fontSize: 13, minWidth: 130 }}
                      >
                        <MenuItem value="weekly" sx={{ fontSize: 13 }}>Semanal</MenuItem>
                        <MenuItem value="monthly" sx={{ fontSize: 13 }}>Mensual</MenuItem>
                      </Select>
                    </div>
                  )}
                </div>

                {/* CHART AREA */}
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-slate-900">
                      {METRIC_OPTIONS.find(m => m.value === selectedMetric)?.label}
                    </h2>
                    <span className="text-xs text-slate-400">Últimos {selectedDays} días</span>
                  </div>
                  <div style={{ minHeight: 380 }} className="flex flex-col justify-center">
                    {selectedMetric === 'pmc' && (
                      hasPMC
                        ? <PMCChart days={pmcData.days} projection={pmcData.projection ?? []} rampRate7d={current.ramp_rate_7d ?? null} height={320} />
                        : <EmptyState message={`Sin actividades en los últimos ${selectedDays} días`} />
                    )}
                    {selectedMetric === 'compliance' && (
                      complianceState.loading
                        ? <Skeleton variant="rectangular" height={320} className="rounded-xl" />
                        : complianceState.error
                          ? <Alert severity="error">{complianceState.error}</Alert>
                          : <ComplianceBarChart buckets={complianceState.data?.buckets ?? []} message={complianceState.data?.message} overallPct={complianceState.data?.overall_pct ?? null} />
                    )}
                    {selectedMetric === 'wellness' && (
                      wellnessState.loading
                        ? <Skeleton variant="rectangular" height={320} className="rounded-xl" />
                        : wellnessState.error
                          ? <Alert severity="error">{wellnessState.error}</Alert>
                          : <WellnessHeatmap entries={wellnessState.data?.entries ?? []} />
                    )}
                    {['vol-run','vol-hours','vol-cycling','effort','strength'].includes(selectedMetric) && (
                      volumeState.loading
                        ? <Skeleton variant="rectangular" height={320} className="rounded-xl" />
                        : volumeState.error
                          ? <Alert severity="error">{volumeState.error}</Alert>
                          : <VolumeBarChart buckets={volumeState.data?.buckets ?? []} metric={volumeState.data?.metric ?? 'distance'} sport={selectedMetric} summary={volumeState.data?.summary ?? null} />
                    )}
                    {selectedMetric === 'zones' && (
                      <div className="flex flex-col items-center justify-center py-16 text-center">
                        <Dumbbell className="w-10 h-10 text-slate-300 mb-3" />
                        <p className="text-slate-600 font-medium">Próximamente</p>
                        <p className="text-slate-400 text-sm mt-1">Tiempo en Zonas requiere datos de zonas HR del dispositivo</p>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ── TAB: Perfil ── */}
        {activeTab === 1 && <AthleteProfileTab membershipId={membershipId} />}

        {/* ── TAB: Lesiones ── */}
        {activeTab === 2 && <AthleteInjuriesTab membershipId={membershipId} />}

        {/* ── TAB: Objetivos ── */}
        {activeTab === 3 && <AthleteGoalsTab membershipId={membershipId} />}

        {/* ── TAB: Wellness ── */}
        {activeTab === 4 && <AthleteWellnessTab membershipId={membershipId} />}

        {/* COACH NOTES — always visible on all tabs */}
        <CoachNotes membershipId={membershipId} />

      </div>

      <ShareReportModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        membershipId={membershipId}
        athleteName={athleteName}
        currentDays={selectedDays}
        previewKPIs={{ readiness_score: readinessScore, ctl, acwr }}
      />
    </Layout>
  )
}

export default CoachAthletePMC
