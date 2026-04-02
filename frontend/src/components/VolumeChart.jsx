import React, { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const MONTHS_ES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

function formatPeriod(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return `${MONTHS_ES[d.getMonth()]} ${d.getDate()}`
}

/** Format raw seconds → "Xh Ym" */
function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  if (m === 0) return `${h}h`
  return `${h}h ${m}m`
}

/** Total hours (fractional) from seconds */
function toHours(seconds) {
  return +(seconds / 3600).toFixed(2)
}

function formatValue(metric, value) {
  if (metric === 'distance') return `${(value / 1000).toFixed(1)} km`
  if (metric === 'duration') return formatDuration(value)
  if (metric === 'elevation') return `${Math.round(value)} m`
  return `${Math.round(value)} TSS`
}

function yLabel(metric) {
  if (metric === 'distance') return 'Distancia (km)'
  if (metric === 'duration') return 'Duración (h)'
  if (metric === 'elevation') return 'Elevación (m)'
  return 'Carga (TSS)'
}

function transform(buckets, metric) {
  return buckets.map(b => ({
    ...b,
    displayValue: metric === 'distance'
      ? +(b.value / 1000).toFixed(2)
      : metric === 'duration'
        ? toHours(b.value)
        : +b.value.toFixed(1),
    label: formatPeriod(b.period_start),
  }))
}

function yAxisTickFormatter(metric) {
  if (metric === 'duration') return (v) => `${v}h`
  if (metric === 'distance') return (v) => `${v}km`
  return undefined
}

const CustomTooltip = ({ active, payload, label, metric, sport }) => {
  if (!active || !payload?.length) return null
  const bucket = payload[0]?.payload ?? {}
  const isRunSport = sport === 'vol-run'
  const isHoursSport = sport === 'vol-hours'
  // D+ shown only for run + cycling, not hours
  const showElev = !isHoursSport && (bucket.elevation_gain_m ?? 0) > 0
  return (
    <div className="bg-white shadow-lg rounded-xl p-3 border border-slate-200 min-w-[190px]">
      <p className="text-xs font-semibold text-slate-700 mb-2">{label}</p>
      <p className="text-xs text-slate-600">
        {yLabel(metric)}:{' '}
        <span className="font-semibold text-amber-500">{formatValue(metric, bucket.value ?? 0)}</span>
      </p>
      {isHoursSport && (
        <p className="text-xs text-slate-600">
          Calorías:{' '}
          <span className="font-semibold text-rose-500">
            {bucket.calories_kcal != null && bucket.calories_kcal > 0
              ? `${Math.round(bucket.calories_kcal).toLocaleString()} kcal`
              : 'N/D'}
          </span>
        </p>
      )}
      {showElev && (
        <p className="text-xs text-slate-600">
          D+: <span className="font-semibold text-orange-500">{Math.round(bucket.elevation_gain_m)} m</span>
        </p>
      )}
      {isRunSport && bucket.avg_gap_formatted && bucket.avg_gap_formatted !== '—' && (
        <p className="text-xs text-slate-600">
          GAP: <span className="font-semibold text-blue-500">{bucket.avg_gap_formatted}/km</span>
        </p>
      )}
      <p className="text-xs text-slate-400 mt-1">{bucket.sessions ?? 0} sesiones</p>
    </div>
  )
}

const ComplianceTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const planned = payload.find(p => p.dataKey === 'planned_sessions')
  const actual = payload.find(p => p.dataKey === 'actual_sessions')
  const pct = payload[0]?.payload?.compliance_pct ?? 0
  return (
    <div className="bg-white shadow-lg rounded-xl p-3 border border-slate-200 min-w-[160px]">
      <p className="text-xs font-semibold text-slate-700 mb-2">{label}</p>
      {planned && <p className="text-xs text-slate-500">Planificadas: <span className="font-semibold text-slate-700">{planned.value}</span></p>}
      {actual && <p className="text-xs text-slate-500">Completadas: <span className="font-semibold text-emerald-600">{actual.value}</span></p>}
      <p className="text-xs text-slate-500 mt-1">Cumplimiento: <span className="font-semibold text-amber-500">{pct}%</span></p>
    </div>
  )
}

export const VolumeBarChart = ({ buckets = [], metric = 'distance', sport = null, summary = null }) => {
  const data = useMemo(() => transform(buckets, metric), [buckets, metric])
  const isRunSport = sport === 'vol-run'
  const isHoursSport = sport === 'vol-hours'
  const tickFmt = yAxisTickFormatter(metric)

  // Compute total hours for KPI display
  const totalSeconds = summary?.total ?? 0
  const totalHoursDisplay = metric === 'duration' ? formatDuration(totalSeconds) : null
  const totalKcal = summary?.total_calories_kcal ?? null

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-slate-500 text-sm">Sin datos de volumen en este período</p>
      </div>
    )
  }

  return (
    <div>
      {/* Summary KPIs */}
      {summary && (
        <div className="flex flex-wrap gap-3 mb-4 text-xs text-slate-600">
          {/* Hours total — only for vol-hours */}
          {isHoursSport && totalHoursDisplay && (
            <span className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
              Total: <strong className="text-amber-700">{totalHoursDisplay}</strong>
            </span>
          )}
          {/* Calories — only for vol-hours */}
          {isHoursSport && (
            <span className="bg-rose-50 border border-rose-200 rounded-lg px-3 py-1.5">
              Calorías:{' '}
              <strong className="text-rose-600">
                {totalKcal != null && totalKcal > 0
                  ? `${Math.round(totalKcal).toLocaleString()} kcal`
                  : 'N/D'}
              </strong>
            </span>
          )}
          {/* GAP — only for vol-run */}
          {isRunSport && summary.avg_gap_formatted && (
            <span className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5">
              GAP promedio: <strong className="text-blue-600">{summary.avg_gap_formatted}/km</strong>
            </span>
          )}
          {/* D+ total — run and cycling, but NOT hours */}
          {!isHoursSport && (summary.total_elevation_gain_m ?? 0) > 0 && (
            <span className="bg-orange-50 border border-orange-200 rounded-lg px-3 py-1.5">
              D+ total: <strong className="text-orange-600">{Math.round(summary.total_elevation_gain_m).toLocaleString()} m</strong>
            </span>
          )}
        </div>
      )}

      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={45}
            tickFormatter={tickFmt}
            label={{ value: yLabel(metric), angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 10, offset: 10 }}
          />
          <Tooltip content={<CustomTooltip metric={metric} sport={sport} />} />
          <Bar dataKey="displayValue" fill="#f59e0b" radius={[4, 4, 0, 0]} maxBarSize={60} name={yLabel(metric)} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export const ComplianceBarChart = ({ buckets = [], message, overallPct = null }) => {
  const data = useMemo(() =>
    buckets.map(b => ({ ...b, label: formatPeriod(b.period_start) })),
    [buckets]
  )

  if (message || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-slate-500 text-sm">{message || 'Sin datos de cumplimiento en este período'}</p>
      </div>
    )
  }

  const totalPlanned = data.reduce((s, b) => s + (b.planned_sessions ?? 0), 0)
  const totalCompleted = data.reduce((s, b) => s + (b.actual_sessions ?? 0), 0)
  const pctDisplay = overallPct != null ? overallPct : (totalPlanned > 0 ? Math.round(totalCompleted / totalPlanned * 100) : null)

  return (
    <div>
      {/* Compliance KPI summary */}
      <div className="flex flex-wrap gap-3 mb-4 text-xs text-slate-600">
        <span className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
          Planificadas: <strong className="text-slate-700">{totalPlanned}</strong>
        </span>
        <span className="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5">
          Completadas: <strong className="text-emerald-700">{totalCompleted}</strong>
        </span>
        {pctDisplay != null && (
          <span className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
            Cumplimiento: <strong className="text-amber-700">{pctDisplay}%</strong>
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={35}
          />
          <Tooltip content={<ComplianceTooltip />} />
          <Bar dataKey="planned_sessions" fill="#cbd5e1" radius={[4, 4, 0, 0]} maxBarSize={40} name="Planificadas" />
          <Bar dataKey="actual_sessions" fill="#10b981" radius={[4, 4, 0, 0]} maxBarSize={40} name="Completadas" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
