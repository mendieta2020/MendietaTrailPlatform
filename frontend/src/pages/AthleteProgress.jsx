import React, { useState, useEffect } from 'react'
import {
  Alert,
  CircularProgress,
  Skeleton,
  Snackbar,
} from '@mui/material'
import { Activity } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import AthleteLayout from '../components/AthleteLayout'
import PMCChart from '../components/PMCChart'
import ARSCard from '../components/ARSCard'
import { useAuth } from '../context/AuthContext'
import { getAthletePMC, getHRProfile, updateHRProfile } from '../api/pmc'

const RANGE_OPTIONS = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
]

const LoadingSkeleton = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {[...Array(4)].map((_, i) => (
        <Skeleton key={i} variant="rectangular" height={120} className="rounded-xl" />
      ))}
    </div>
    <Skeleton variant="rectangular" height={380} className="rounded-xl" />
    <Skeleton variant="rectangular" height={160} className="rounded-xl" />
  </div>
)

const AthleteProgress = () => {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [selectedDays, setSelectedDays] = useState(90)
  const [pmcData, setPmcData] = useState(null)
  const [hrProfile, setHrProfile] = useState({ hr_max: '', hr_rest: '' })
  const [loadingPMC, setLoadingPMC] = useState(true)
  const [errorPMC, setErrorPMC] = useState(null)
  const [savingHR, setSavingHR] = useState(false)
  const [hrSuccess, setHrSuccess] = useState(false)
  const [hrError, setHrError] = useState(null)

  useEffect(() => {
    setLoadingPMC(true)
    setErrorPMC(null)
    getAthletePMC(selectedDays)
      .then(res => setPmcData(res.data))
      .catch(() => setErrorPMC('No se pudieron cargar los datos de rendimiento. Intenta de nuevo.'))
      .finally(() => setLoadingPMC(false))
  }, [selectedDays])

  useEffect(() => {
    getHRProfile()
      .then(res => setHrProfile({ hr_max: res.data.hr_max ?? '', hr_rest: res.data.hr_rest ?? '' }))
      .catch(() => {})
  }, [])

  const handleSaveHR = async () => {
    setSavingHR(true)
    setHrError(null)
    try {
      await updateHRProfile(hrProfile)
      setHrSuccess(true)
    } catch {
      setHrError('No se pudo guardar el perfil. Intenta de nuevo.')
    } finally {
      setSavingHR(false)
    }
  }

  const hasData = pmcData && pmcData.days && pmcData.days.length > 0

  return (
    <AthleteLayout user={user}>
      <div className="p-6 space-y-6">
        {/* HEADER */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Mi Progreso</h1>
            <p className="text-sm text-slate-500 mt-1">Análisis fisiológico de rendimiento</p>
          </div>
          <div className="flex gap-2">
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
        </div>

        {/* ERROR */}
        {errorPMC && (
          <Alert severity="error" onClose={() => setErrorPMC(null)}>
            {errorPMC}
          </Alert>
        )}

        {/* LOADING */}
        {loadingPMC && <LoadingSkeleton />}

        {/* EMPTY STATE */}
        {!loadingPMC && !errorPMC && !hasData && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Activity className="w-12 h-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-semibold text-slate-700">Aún no hay datos de rendimiento</h3>
            <p className="text-sm text-slate-500 mt-1 mb-6">
              Conecta tu dispositivo y completa tu primera actividad para ver tu PMC.
            </p>
            <button
              onClick={() => navigate('/connections')}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Conectar dispositivo
            </button>
          </div>
        )}

        {/* DATA */}
        {!loadingPMC && !errorPMC && hasData && (
          <>
            {/* ARS CARDS */}
            <ARSCard
              ars={pmcData.ars ?? 0}
              tsb_zone={pmcData.tsb_zone ?? ''}
              ars_label={pmcData.ars_label ?? ''}
              ctl={pmcData.ctl ?? 0}
              atl={pmcData.atl ?? 0}
              tsb={pmcData.tsb ?? 0}
            />

            {/* PMC CHART */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-slate-900">Performance Management Chart</h2>
                <span className="text-xs text-slate-400">Últimos {selectedDays} días</span>
              </div>
              <PMCChart days={pmcData.days} height={320} />
            </div>

            {/* HR PROFILE */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
              <h2 className="text-lg font-semibold text-slate-900 mb-1">Perfil de Frecuencia Cardíaca</h2>
              <p className="text-xs text-slate-500 mb-4">
                Configurar tus valores reales mejora la precisión del análisis TRIMP.
              </p>
              {hrError && (
                <Alert severity="error" onClose={() => setHrError(null)} className="mb-4">
                  {hrError}
                </Alert>
              )}
              <div className="flex flex-col sm:flex-row gap-4 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-slate-700 mb-1">HR Máxima (bpm)</label>
                  <input
                    type="number"
                    value={hrProfile.hr_max}
                    onChange={e => setHrProfile(p => ({ ...p, hr_max: e.target.value }))}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                    placeholder="180"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs font-medium text-slate-700 mb-1">HR en Reposo (bpm)</label>
                  <input
                    type="number"
                    value={hrProfile.hr_rest}
                    onChange={e => setHrProfile(p => ({ ...p, hr_rest: e.target.value }))}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                    placeholder="50"
                  />
                </div>
                <button
                  onClick={handleSaveHR}
                  disabled={savingHR}
                  className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {savingHR && <CircularProgress size={16} color="inherit" />}
                  {savingHR ? 'Guardando…' : 'Guardar'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <Snackbar
        open={hrSuccess}
        autoHideDuration={3000}
        onClose={() => setHrSuccess(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" onClose={() => setHrSuccess(false)}>
          Perfil actualizado correctamente
        </Alert>
      </Snackbar>
    </AthleteLayout>
  )
}

export default AthleteProgress
