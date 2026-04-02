import React, { useState, useEffect } from 'react'
import { Alert, Skeleton } from '@mui/material'
import { BarChart2, Users, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer } from 'recharts'
import Layout from '../components/Layout'
import { getTeamReadiness } from '../api/pmc'

function tsbColor(tsb) {
  if (tsb >= 25) return 'text-slate-600'
  if (tsb >= 0) return 'text-green-600'
  if (tsb >= -10) return 'text-amber-600'
  if (tsb >= -30) return 'text-orange-600'
  return 'text-red-600'
}

function tsbBadgeClass(zone) {
  const map = {
    fresh: 'bg-slate-100 text-slate-700',
    optimal: 'bg-green-100 text-green-700',
    productive: 'bg-amber-100 text-amber-700',
    fatigued: 'bg-orange-100 text-orange-700',
    overreaching: 'bg-red-100 text-red-700',
  }
  return map[zone] ?? 'bg-slate-100 text-slate-700'
}

function tsbZoneLabel(zone) {
  const map = {
    fresh: 'Muy fresco',
    optimal: 'En forma',
    productive: 'Cargando bien',
    fatigued: 'Carga alta',
    overreaching: 'En riesgo',
  }
  return map[zone] ?? zone
}

function tsbSign(val) {
  return val >= 0 ? `+${Math.round(val)}` : `${Math.round(val)}`
}

function rampBadgeClass(rate) {
  if (rate === null || rate === undefined) return 'bg-slate-100 text-slate-500'
  if (rate > 10) return 'bg-red-100 text-red-700'
  if (rate > 8) return 'bg-amber-100 text-amber-700'
  if (rate >= 3) return 'bg-green-100 text-green-700'
  if (rate >= 0) return 'bg-slate-100 text-slate-600'
  return 'bg-blue-100 text-blue-700'
}

function rampSign(rate) {
  if (rate === null || rate === undefined) return '—'
  return rate >= 0 ? `+${rate}` : `${rate}`
}

const MiniSparkline = ({ data = [], zone }) => {
  const color = {
    fresh: '#64748b',
    optimal: '#10b981',
    productive: '#f59e0b',
    fatigued: '#f97316',
    overreaching: '#ef4444',
  }[zone] ?? '#3b82f6'

  return (
    <ResponsiveContainer width={80} height={32}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="ctl"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

const SUMMARY_CARDS_CONFIG = [
  {
    key: 'overreaching',
    bg: '#fef2f2',
    borderColor: '#fca5a5',
    accentColor: '#ef4444',
    numColor: '#dc2626',
    label: 'En riesgo',
    sub: 'TSB < -30',
  },
  {
    key: 'fatigued',
    bg: '#fff7ed',
    borderColor: '#fdba74',
    accentColor: '#f97316',
    numColor: '#ea580c',
    label: 'Carga alta',
    sub: 'TSB -30 a -10',
  },
  {
    key: 'productive',
    bg: '#fffbeb',
    borderColor: '#fcd34d',
    accentColor: '#f59e0b',
    numColor: '#d97706',
    label: 'Cargando bien',
    sub: 'TSB -10 a 0',
  },
  {
    key: 'optimal',
    bg: '#f0fdf4',
    borderColor: '#86efac',
    accentColor: '#22c55e',
    numColor: '#16a34a',
    label: 'En forma',
    sub: 'TSB 0 a +25',
  },
  {
    key: 'fresh',
    bg: '#f8fafc',
    borderColor: '#cbd5e1',
    accentColor: '#94a3b8',
    numColor: '#475569',
    label: 'Muy fresco',
    sub: 'TSB > +25',
  },
]

const SummaryCards = ({ summary = {} }) => {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {SUMMARY_CARDS_CONFIG.map(({ key, bg, borderColor, accentColor, numColor, label, sub }) => (
        <div
          key={key}
          className="rounded-xl p-4"
          style={{
            background: bg,
            border: `1px solid ${borderColor}`,
            borderLeft: `4px solid ${accentColor}`,
          }}
        >
          <p className="text-3xl font-bold" style={{ color: numColor }}>{summary[key] ?? 0}</p>
          <p className="text-sm font-semibold text-slate-700 mt-1">{label}</p>
          <p className="text-xs text-slate-500">{sub}</p>
        </div>
      ))}
    </div>
  )
}

const CoachAnalytics = () => {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getTeamReadiness()
      .then(res => setData(res.data))
      .catch(() => setError('No se pudieron cargar los datos del equipo. Intenta de nuevo.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <Layout>
      <div className="p-6 space-y-6">
        {/* HEADER */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics del Equipo</h1>
          <p className="text-sm text-slate-500 mt-1">Estado fisiológico en tiempo real de todos tus atletas</p>
        </div>

        {/* ERROR */}
        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* LOADING */}
        {loading && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} variant="rectangular" height={100} className="rounded-xl" />
              ))}
            </div>
            <Skeleton variant="rectangular" height={400} className="rounded-xl" />
          </div>
        )}

        {!loading && !error && data && (
          <>
            {/* SUMMARY CARDS */}
            <SummaryCards summary={data.summary ?? {}} />

            {/* ATHLETE TABLE */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200">
              <div className="px-6 py-4 border-b border-slate-100">
                <h2 className="text-lg font-semibold text-slate-900">Estado del equipo</h2>
              </div>

              {(!data.athletes || data.athletes.length === 0) ? (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                  <Users className="w-12 h-12 text-slate-300 mb-4" />
                  <h3 className="text-lg font-semibold text-slate-700">No hay atletas con datos aún</h3>
                  <p className="text-sm text-slate-500 mt-1">
                    Los atletas aparecerán aquí una vez que completen su primera actividad.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-100">
                        {['ATLETA', 'CTL', 'ATL', 'TSB', 'ESTADO', 'GAP', 'RAMP 7D', 'TENDENCIA', ''].map((h, i) => (
                          <th
                            key={i}
                            className="text-xs uppercase tracking-wide text-slate-500 px-6 py-3 text-left font-medium"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.athletes.map(a => (
                        <tr
                          key={a.membership_id}
                          className="hover:bg-slate-50 cursor-pointer border-b border-slate-50 transition-colors"
                          onClick={() => navigate(`/coach/athletes/${a.membership_id}/pmc`)}
                        >
                          <td className="px-6 py-4 font-medium text-slate-900 text-sm">{a.name}</td>
                          <td className="px-6 py-4 text-blue-600 font-semibold text-sm">{Math.round(a.ctl)}</td>
                          <td className="px-6 py-4 text-orange-500 font-semibold text-sm">{Math.round(a.atl)}</td>
                          <td className={`px-6 py-4 font-semibold text-sm ${tsbColor(a.tsb)}`}>
                            {tsbSign(a.tsb)}
                          </td>
                          <td className="px-6 py-4">
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tsbBadgeClass(a.tsb_zone)}`}>
                              {tsbZoneLabel(a.tsb_zone)}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm text-slate-600 font-mono">
                            {a.avg_gap_formatted ?? '—'}
                          </td>
                          <td className="px-6 py-4">
                            {a.ramp_rate_7d !== undefined ? (
                              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${rampBadgeClass(a.ramp_rate_7d)}`}>
                                {rampSign(a.ramp_rate_7d)}
                              </span>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            <MiniSparkline data={a.trend_14d ?? []} zone={a.tsb_zone} />
                          </td>
                          <td className="px-6 py-4">
                            <ChevronRight className="w-4 h-4 text-slate-300" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </Layout>
  )
}

export default CoachAnalytics
