import React from 'react'
import { Tooltip } from '@mui/material'
import { TrendingUp, Zap, Activity } from 'lucide-react'

const TOOLTIPS = {
  ars: 'Índice de disposición 0-100. Combina carga de entrenamiento y bienestar. >75 = listo para entrenar fuerte.',
  ctl: 'Fitness acumulado en 42 días. Mayor número = más preparado. Se construye con entrenamiento consistente.',
  atl: 'Fatiga de los últimos 7 días. Número alto = mucha carga reciente. Necesita descanso para bajar.',
  tsb: 'Balance fitness menos fatiga. Positivo = fresco para competir. Negativo = en fase de construcción.',
}

function arsColor(ars) {
  if (ars >= 75) return 'text-green-500'
  if (ars >= 50) return 'text-amber-500'
  return 'text-red-500'
}

function arsBorderColor(ars) {
  if (ars >= 75) return 'border-l-green-500'
  if (ars >= 50) return 'border-l-amber-500'
  return 'border-l-red-500'
}

function tsbColor(tsb) {
  return tsb >= 0 ? 'text-emerald-500' : 'text-red-500'
}

function tsbSubtext(tsb) {
  if (tsb >= 25) return 'Muy fresco — listo para competir'
  if (tsb >= 0) return 'Ventana de rendimiento óptimo'
  if (tsb >= -10) return 'Carga productiva'
  if (tsb >= -30) return 'Fatiga acumulada'
  return 'Riesgo de sobreentrenamiento'
}

const ARSCard = ({ ars = 0, ars_label = '', ctl = 0, atl = 0, tsb = 0 }) => {
  const tsbDisplay = tsb >= 0 ? `+${Math.round(tsb)}` : `${Math.round(tsb)}`

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {/* CARD 1 — ARS */}
      <Tooltip title={TOOLTIPS.ars} placement="top" arrow>
        <div className={`bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 ${arsBorderColor(ars)} p-6 cursor-help`}>
          <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">ARS</p>
          <p className={`text-5xl font-bold ${arsColor(ars)} leading-none`}>{Math.round(ars)}</p>
          <p className="text-sm font-medium text-slate-500 mt-2">{ars_label || 'Estado de forma'}</p>
        </div>
      </Tooltip>

      {/* CARD 2 — CTL */}
      <Tooltip title={TOOLTIPS.ctl} placement="top" arrow>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-blue-500 p-6 cursor-help">
          <div className="flex items-start justify-between">
            <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">CTL — Forma</p>
            <TrendingUp className="w-4 h-4 text-blue-400" />
          </div>
          <p className="text-3xl font-bold text-blue-500 leading-none">{Math.round(ctl)}</p>
          <p className="text-xs text-slate-500 mt-2">Fitness acumulado (42 días)</p>
        </div>
      </Tooltip>

      {/* CARD 3 — ATL */}
      <Tooltip title={TOOLTIPS.atl} placement="top" arrow>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-orange-500 p-6 cursor-help">
          <div className="flex items-start justify-between">
            <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">ATL — Fatiga</p>
            <Zap className="w-4 h-4 text-orange-400" />
          </div>
          <p className="text-3xl font-bold text-orange-500 leading-none">{Math.round(atl)}</p>
          <p className="text-xs text-slate-500 mt-2">Carga reciente (7 días)</p>
        </div>
      </Tooltip>

      {/* CARD 4 — TSB */}
      <Tooltip title={TOOLTIPS.tsb} placement="top" arrow>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-emerald-500 p-6 cursor-help">
          <div className="flex items-start justify-between">
            <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">TSB — Balance</p>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <p className={`text-3xl font-bold ${tsbColor(tsb)} leading-none`}>{tsbDisplay}</p>
          <p className="text-xs text-slate-500 mt-2">{tsbSubtext(tsb)}</p>
        </div>
      </Tooltip>
    </div>
  )
}

export default ARSCard
