import React, { useState, useReducer, useEffect } from 'react'
import { Alert, Skeleton } from '@mui/material'
import { ChevronLeft } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../components/Layout'
import PMCChart from '../components/PMCChart'
import ARSCard from '../components/ARSCard'
import { getCoachAthletePMC } from '../api/pmc'

function fetchReducer(state, action) {
  switch (action.type) {
    case 'FETCH': return { loading: true, error: null, data: state.data }
    case 'OK': return { loading: false, error: null, data: action.data }
    case 'ERR': return { loading: false, error: action.error, data: null }
    case 'CLEAR_ERROR': return { ...state, error: null }
    default: return state
  }
}

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
  </div>
)

const CoachAthletePMC = () => {
  const navigate = useNavigate()
  const { membershipId } = useParams()
  const [selectedDays, setSelectedDays] = useState(90)
  const [{ loading, error, data: pmcData }, dispatch] = useReducer(fetchReducer, {
    loading: true, error: null, data: null,
  })

  useEffect(() => {
    dispatch({ type: 'FETCH' })
    getCoachAthletePMC(membershipId, selectedDays)
      .then(res => dispatch({ type: 'OK', data: res.data }))
      .catch(() => dispatch({ type: 'ERR', error: 'No se pudieron cargar los datos del atleta. Intenta de nuevo.' }))
  }, [membershipId, selectedDays])

  const athleteName = pmcData?.athlete_name ?? 'Atleta'
  const hasData = pmcData && pmcData.days && pmcData.days.length > 0

  return (
    <Layout>
      <div className="p-6 space-y-6">
        {/* BACK BUTTON */}
        <button
          onClick={() => navigate('/coach/analytics')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Volver al equipo
        </button>

        {/* HEADER */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{athleteName} — PMC</h1>
            <p className="text-sm text-slate-500">Performance Management Chart</p>
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
        {error && (
          <Alert severity="error" onClose={() => dispatch({ type: 'CLEAR_ERROR' })}>
            {error}
          </Alert>
        )}

        {/* LOADING */}
        {loading && <LoadingSkeleton />}

        {/* DATA */}
        {!loading && !error && hasData && (
          <>
            <ARSCard
              ars={pmcData.ars ?? 0}
              tsb_zone={pmcData.tsb_zone ?? ''}
              ars_label={pmcData.ars_label ?? ''}
              ctl={pmcData.ctl ?? 0}
              atl={pmcData.atl ?? 0}
              tsb={pmcData.tsb ?? 0}
            />
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-slate-900">Performance Management Chart</h2>
                <span className="text-xs text-slate-400">Últimos {selectedDays} días</span>
              </div>
              <PMCChart days={pmcData.days} height={320} />
            </div>
          </>
        )}

        {/* EMPTY STATE */}
        {!loading && !error && !hasData && pmcData && (
          <div className="flex flex-col items-center justify-center py-20 text-center bg-white rounded-xl shadow-sm border border-slate-200">
            <p className="text-lg font-semibold text-slate-700">Sin datos para este período</p>
            <p className="text-sm text-slate-500 mt-1">
              El atleta no tiene actividades registradas en los últimos {selectedDays} días.
            </p>
          </div>
        )}
      </div>
    </Layout>
  )
}

export default CoachAthletePMC
