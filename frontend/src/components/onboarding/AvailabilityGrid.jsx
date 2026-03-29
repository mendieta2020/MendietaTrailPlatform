import React from 'react';
import { TextField, MenuItem } from '@mui/material';
import { Check, X } from 'lucide-react';

const DAYS = [
  { value: 0, label: 'Lun', full: 'Lunes' },
  { value: 1, label: 'Mar', full: 'Martes' },
  { value: 2, label: 'Mié', full: 'Miércoles' },
  { value: 3, label: 'Jue', full: 'Jueves' },
  { value: 4, label: 'Vie', full: 'Viernes' },
  { value: 5, label: 'Sáb', full: 'Sábado' },
  { value: 6, label: 'Dom', full: 'Domingo' },
];

const TIME_OPTIONS = [
  { value: '', label: 'Sin preferencia' },
  { value: 'morning', label: 'Mañana' },
  { value: 'afternoon', label: 'Tarde' },
  { value: 'evening', label: 'Noche' },
];

export default function AvailabilityGrid({ value, onChange }) {
  const toggleDay = (dayIndex) => {
    const updated = value.map((entry) =>
      entry.day_of_week === dayIndex
        ? { ...entry, is_available: !entry.is_available, reason: '' }
        : entry
    );
    onChange(updated);
  };

  const updateField = (dayIndex, field, val) => {
    const updated = value.map((entry) =>
      entry.day_of_week === dayIndex ? { ...entry, [field]: val } : entry
    );
    onChange(updated);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-slate-700 mb-2">
        Disponibilidad semanal para entrenar
      </p>

      {/* Desktop: horizontal grid */}
      <div className="hidden sm:grid sm:grid-cols-7 gap-2">
        {DAYS.map((day) => {
          const entry = value.find((e) => e.day_of_week === day.value);
          const available = entry?.is_available ?? true;
          return (
            <button
              key={day.value}
              type="button"
              onClick={() => toggleDay(day.value)}
              className={`flex flex-col items-center gap-1 p-3 rounded-xl border-2 transition-all ${
                available
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-600'
              }`}
            >
              <span className="text-xs font-semibold uppercase">{day.label}</span>
              {available ? (
                <Check className="w-5 h-5" />
              ) : (
                <X className="w-5 h-5" />
              )}
            </button>
          );
        })}
      </div>

      {/* Mobile: vertical list */}
      <div className="sm:hidden space-y-2">
        {DAYS.map((day) => {
          const entry = value.find((e) => e.day_of_week === day.value);
          const available = entry?.is_available ?? true;
          return (
            <div key={day.value} className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => toggleDay(day.value)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all flex-1 ${
                  available
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-red-200 bg-red-50 text-red-600'
                }`}
              >
                {available ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                <span className="text-sm font-medium">{day.full}</span>
              </button>
            </div>
          );
        })}
      </div>

      {/* Unavailable day details */}
      {value
        .filter((e) => !e.is_available)
        .map((entry) => {
          const day = DAYS.find((d) => d.value === entry.day_of_week);
          return (
            <div key={`detail-${entry.day_of_week}`} className="bg-slate-50 rounded-xl p-3 space-y-2">
              <p className="text-xs font-semibold text-slate-500 uppercase">
                {day?.full} — No disponible
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <TextField
                  size="small"
                  label="Motivo"
                  placeholder="Ej: Trabajo, estudios..."
                  value={entry.reason || ''}
                  onChange={(e) => updateField(entry.day_of_week, 'reason', e.target.value)}
                  fullWidth
                />
                <TextField
                  size="small"
                  select
                  label="Horario preferido"
                  value={entry.preferred_time || ''}
                  onChange={(e) => updateField(entry.day_of_week, 'preferred_time', e.target.value)}
                  fullWidth
                >
                  {TIME_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                  ))}
                </TextField>
              </div>
            </div>
          );
        })}

      <p className="text-xs text-slate-400">
        Tocá cada día para indicar si podés entrenar. Los días no disponibles aparecerán bloqueados en tu calendario.
      </p>
    </div>
  );
}
