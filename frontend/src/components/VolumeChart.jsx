import React, { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
} from 'recharts'

const MONTHS_ES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

function formatPeriod(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return `${MONTHS_ES[d.getMonth()]} ${d.getDate()}`
}

function formatValue(metric, value) {
  if (metric === 'distance') return `${(value / 1000).toFixed(1)} km`
  if (metric === 'duration') return `${Math.round(value / 60)} min`
  if (metric === 'elevation') return `${Math.round(value)} m`
  return `${Math.round(value)} TSS`
}

function yLabel(metric) {
  if (metric === 'distance') return 'Distancia (km)'
  if (metric === 'duration') return 'Duración (min)'
  if (metric === 'elevation') return 'Elevación (m)'
  return 'Carga (TSS)'
}

function transform(buckets, metric) {
  return buckets.map(b => ({
    ...b,
    displayValue: metric === 'distance'
      ? +(b.value / 1000).toFixed(2)
      : metric === 'duration'
        ? +(b.value / 60).toFixed(1)
        : +b.value.toFixed(1),
    label: formatPeriod(b.period_start),
  }))
}

const CustomTooltip = ({ active, payload, label, metric }) => {
  if (!active || !payload?.length) return null
  const bar = payload.find(p => p.dataKey === 'displayValue')
  return (
    <div className="bg-white shadow-lg rounded-xl p-3 border border-slate-200 min-w-[160px]">
      <p className="text-xs font-semibold text-slate-700 mb-2">{label}</p>
      {bar && (
        <p className="text-xs text-slate-600">
          {yLabel(metric)}:{' '}
          <span className="font-semibold text-amber-500">{formatValue(metric, payload[0]?.payload?.value ?? 0)}</span>
        </p>
      )}
      <p className="text-xs text-slate-400 mt-1">{payload[0]?.payload?.sessions ?? 0} sesiones</p>
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

export const VolumeBarChart = ({ buckets = [], metric = 'distance' }) => {
  const data = useMemo(() => transform(buckets, metric), [buckets, metric])

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-slate-500 text-sm">Sin datos de volumen en este período</p>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
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
          label={{ value: yLabel(metric), angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 10, offset: 10 }}
        />
        <Tooltip content={<CustomTooltip metric={metric} />} />
        <Bar dataKey="displayValue" fill="#f59e0b" radius={[4, 4, 0, 0]} maxBarSize={60} name={yLabel(metric)} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export const ComplianceBarChart = ({ buckets = [], message }) => {
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

  return (
    <ResponsiveContainer width="100%" height={320}>
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
  )
}
