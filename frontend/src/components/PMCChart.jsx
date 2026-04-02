import React, { useMemo, useState } from 'react'
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { Tooltip as MuiTooltip } from '@mui/material'

const MONTHS_ES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
const DAYS_ES = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado']

function formatXAxis(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return `${MONTHS_ES[d.getMonth()]} ${d.getDate()}`
}

function formatFullDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return `${DAYS_ES[d.getDay()]} ${d.getDate()} de ${MONTHS_ES[d.getMonth()]}`
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null
  const ctl = payload.find(p => p.dataKey === 'ctl')
  const atl = payload.find(p => p.dataKey === 'atl')
  const tsb = payload.find(p => p.dataKey === 'tsb')
  const tss = payload.find(p => p.dataKey === 'tss')
  const tsbVal = tsb?.value ?? 0

  return (
    <div className="bg-white shadow-lg rounded-xl p-3 border border-slate-200 min-w-[180px]">
      <p className="text-xs font-semibold text-slate-700 mb-2">{formatFullDate(label)}</p>
      {ctl && (
        <p className="text-xs text-slate-600">
          CTL: <span className="font-semibold text-blue-500">{ctl.value?.toFixed(1)}</span>
        </p>
      )}
      {atl && (
        <p className="text-xs text-slate-600">
          ATL: <span className="font-semibold text-orange-500">{atl.value?.toFixed(1)}</span>
        </p>
      )}
      {tsb && (
        <p className="text-xs text-slate-600">
          TSB:{' '}
          <span className={`font-semibold ${tsbVal >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
            {tsbVal >= 0 ? '+' : ''}{tsbVal?.toFixed(1)}
          </span>
        </p>
      )}
      {tss && (
        <p className="text-xs text-slate-600">
          TSS: <span className="font-semibold text-slate-700">{tss.value?.toFixed(0)}</span>
        </p>
      )}
    </div>
  )
}

function rampRateColor(rate) {
  if (rate === null || rate === undefined) return 'text-slate-400'
  if (rate > 10) return 'text-red-500'
  if (rate > 8) return 'text-amber-500'
  if (rate >= 3) return 'text-green-600'
  if (rate >= 0) return 'text-slate-500'
  return 'text-blue-500'
}

function rampRateSign(rate) {
  if (rate > 0) return `+${rate}`
  return `${rate}`
}

// Legend items with their chart dataKey for hover highlighting
const LEGEND_ITEMS = [
  { key: 'ctl',          label: 'CTL — Forma',     color: '#3b82f6', dash: false },
  { key: 'atl',          label: 'ATL — Fatiga',    color: '#f97316', dash: false },
  { key: 'tsb',          label: 'TSB — Balance',   color: '#10b981', dash: false },
  { key: 'ctlProjected', label: 'Proyección CTL',  color: '#93c5fd', dash: true  },
]

const CustomLegend = ({ rampRate7d, hoveredLine, onHover, onHoverEnd }) => (
  <div className="flex flex-wrap items-center justify-center gap-5 mt-3">
    {LEGEND_ITEMS.map(({ key, label, color, dash }) => (
      <div
        key={key}
        className="flex items-center gap-1.5 cursor-pointer select-none"
        onMouseEnter={() => onHover(key)}
        onMouseLeave={onHoverEnd}
        style={{ opacity: hoveredLine && hoveredLine !== key ? 0.4 : 1, transition: 'opacity 0.15s' }}
      >
        <div
          className="w-4 h-0.5 rounded"
          style={{
            background: dash ? 'transparent' : color,
            borderTop: dash ? `2px dashed ${color}` : 'none',
            height: dash ? 0 : 2,
          }}
        />
        <span className="text-xs text-slate-500">{label}</span>
      </div>
    ))}
    {rampRate7d !== null && rampRate7d !== undefined && (
      <MuiTooltip
        title="Velocidad de cambio de fitness. +5 a +8 por semana es crecimiento óptimo."
        placement="top"
        arrow
      >
        <span className={`text-xs font-semibold cursor-help ${rampRateColor(rampRate7d)}`}>
          Ramp Rate: {rampRateSign(rampRate7d)} CTL/sem
        </span>
      </MuiTooltip>
    )}
  </div>
)

// Label component for "Hoy" on the reference line
const TodayLabel = ({ viewBox }) => {
  if (!viewBox) return null
  return (
    <text
      x={viewBox.x + 4}
      y={viewBox.y + 14}
      fill="#475569"
      fontSize={10}
      fontWeight={600}
    >
      Hoy
    </text>
  )
}

const PMCChart = ({ days = [], projection = [], rampRate7d = null, height = 320 }) => {
  const [hoveredLine, setHoveredLine] = useState(null)

  // Merge historical + projection into one dataset
  const chartData = useMemo(() => {
    const historical = days.map(d => ({
      ...d,
      tsbPos: d.tsb > 0 ? d.tsb : 0,
      tsbNeg: d.tsb < 0 ? d.tsb : 0,
      ctlProjected: undefined,
    }))
    const projected = projection.map(p => ({
      date: p.date,
      tss: null,
      ctl: null,
      atl: null,
      tsb: null,
      ars: null,
      tsbPos: 0,
      tsbNeg: 0,
      ctlProjected: p.ctl,
    }))
    return [...historical, ...projected]
  }, [days, projection])

  const projectionTodayStr = useMemo(() => new Date().toISOString().slice(0, 10), [])

  // Per-line style based on hover state
  function lineStyle(key) {
    const dimmed = hoveredLine !== null && hoveredLine !== key
    return {
      strokeWidth: hoveredLine === key ? 3 : 2,
      opacity: dimmed ? 0.25 : 1,
    }
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tickFormatter={formatXAxis}
          tick={{ fill: '#94a3b8', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          minTickGap={30}
        />
        <YAxis
          yAxisId="left"
          domain={[0, 'auto']}
          tick={{ fill: '#94a3b8', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={35}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          domain={[-60, 60]}
          tick={{ fill: '#94a3b8', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={35}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          content={
            <CustomLegend
              rampRate7d={rampRate7d}
              hoveredLine={hoveredLine}
              onHover={setHoveredLine}
              onHoverEnd={() => setHoveredLine(null)}
            />
          }
        />

        {/* TSB positive area — green */}
        <Area
          yAxisId="right"
          type="monotone"
          dataKey="tsbPos"
          stroke="none"
          fill="#10b981"
          fillOpacity={hoveredLine === 'tsb' ? 0.35 : hoveredLine ? 0.08 : 0.2}
          legendType="none"
          name=""
          tooltipType="none"
          isAnimationActive={false}
        />
        {/* TSB negative area — red */}
        <Area
          yAxisId="right"
          type="monotone"
          dataKey="tsbNeg"
          stroke="none"
          fill="#ef4444"
          fillOpacity={hoveredLine === 'tsb' ? 0.35 : hoveredLine ? 0.08 : 0.2}
          legendType="none"
          name=""
          tooltipType="none"
          isAnimationActive={false}
        />

        {/* Zero reference line */}
        <ReferenceLine yAxisId="right" y={0} stroke="#cbd5e1" strokeDasharray="4 4" />

        {/* "Zona de fatiga" label in the red negative area */}
        <ReferenceLine
          yAxisId="right"
          y={-20}
          stroke="transparent"
          label={{ value: 'Zona de fatiga', position: 'insideBottomRight', fill: '#ef4444', fillOpacity: 0.45, fontSize: 10 }}
        />

        {/* Today marker — visible divider between history and projection */}
        {projection.length > 0 && (
          <ReferenceLine
            yAxisId="left"
            x={projectionTodayStr}
            stroke="#475569"
            strokeWidth={2}
            label={<TodayLabel />}
          />
        )}

        <Line
          yAxisId="left"
          type="monotone"
          dataKey="ctl"
          stroke="#3b82f6"
          strokeWidth={lineStyle('ctl').strokeWidth}
          opacity={lineStyle('ctl').opacity}
          dot={false}
          name="CTL (Forma)"
          connectNulls={false}
        />
        {/* CTL projection — dashed, lighter blue */}
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="ctlProjected"
          stroke="#93c5fd"
          strokeWidth={lineStyle('ctlProjected').strokeWidth + 0.5}
          opacity={lineStyle('ctlProjected').opacity}
          strokeDasharray="5 5"
          dot={false}
          name="Proyección CTL"
          legendType="none"
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="atl"
          stroke="#f97316"
          strokeWidth={lineStyle('atl').strokeWidth}
          opacity={lineStyle('atl').opacity}
          dot={false}
          name="ATL (Fatiga)"
          connectNulls={false}
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="tsb"
          stroke="#10b981"
          strokeWidth={lineStyle('tsb').strokeWidth}
          opacity={lineStyle('tsb').opacity}
          dot={false}
          name="TSB (Balance)"
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export default PMCChart
