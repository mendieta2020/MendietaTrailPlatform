import React, { useMemo } from 'react'

const DIMENSIONS = [
  { key: 'sleep', label: 'Sueño' },
  { key: 'energy', label: 'Energía' },
  { key: 'mood', label: 'Ánimo' },
  { key: 'soreness', label: 'Dolor' },
  { key: 'stress', label: 'Estrés' },
]

function cellColor(value) {
  if (!value) return '#f1f5f9'  // no data
  if (value <= 1) return '#ef4444'
  if (value <= 2) return '#f97316'
  if (value <= 3) return '#eab308'
  if (value <= 4) return '#84cc16'
  return '#22c55e'
}

const WellnessHeatmap = ({ entries = [] }) => {
  const dates = useMemo(() => entries.map(e => e.date), [entries])
  const entryByDate = useMemo(() => {
    const map = {}
    entries.forEach(e => { map[e.date] = e })
    return map
  }, [entries])

  // Show every 7th date label
  const dateLabelSet = useMemo(() => {
    const set = new Set()
    dates.filter((_, i) => i % 7 === 0).forEach(d => set.add(d))
    return set
  }, [dates])

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-slate-500 text-sm">Sin datos de bienestar en este período</p>
        <p className="text-slate-400 text-xs mt-1">El atleta aún no ha completado ningún check-in</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[600px]">
        {/* Color legend */}
        <div className="flex items-center gap-3 mb-4 text-xs text-slate-500">
          <span>Escala:</span>
          {[1, 2, 3, 4, 5].map(v => (
            <div key={v} className="flex items-center gap-1">
              <div
                className="w-4 h-4 rounded"
                style={{ backgroundColor: cellColor(v) }}
              />
              <span>{v}</span>
            </div>
          ))}
          <div className="flex items-center gap-1">
            <div className="w-4 h-4 rounded bg-slate-100 border border-slate-200" />
            <span>Sin dato</span>
          </div>
        </div>

        {/* Grid */}
        <div className="space-y-1">
          {DIMENSIONS.map(dim => (
            <div key={dim.key} className="flex items-center gap-2">
              {/* Row label */}
              <div className="w-16 text-right text-xs text-slate-500 shrink-0">{dim.label}</div>
              {/* Cells */}
              <div className="flex gap-0.5 flex-1">
                {dates.map(date => {
                  const entry = entryByDate[date]
                  const val = entry?.[dim.key]
                  return (
                    <div
                      key={date}
                      title={`${date}: ${dim.label} = ${val ?? '—'}`}
                      className="h-6 rounded-sm flex-1 min-w-[8px]"
                      style={{ backgroundColor: cellColor(val) }}
                    />
                  )
                })}
              </div>
            </div>
          ))}

          {/* Date labels */}
          <div className="flex items-center gap-2 mt-1">
            <div className="w-16 shrink-0" />
            <div className="flex gap-0.5 flex-1">
              {dates.map(date => (
                <div
                  key={date}
                  className="flex-1 min-w-[8px] text-center"
                >
                  {dateLabelSet.has(date) && (
                    <span className="text-[10px] text-slate-400 block truncate">
                      {date.slice(5)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WellnessHeatmap
