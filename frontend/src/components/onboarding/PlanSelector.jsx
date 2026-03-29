import React from 'react';
import { Check } from 'lucide-react';

function formatARS(amount) {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(amount);
}

export default function PlanSelector({ plans, selectedPlanId, onSelect }) {
  if (!plans || plans.length === 0) return null;

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-slate-700 mb-2">
        Elegí tu plan de entrenamiento
      </p>
      {plans.map((plan) => {
        const isSelected = selectedPlanId === plan.id;
        return (
          <button
            key={plan.id}
            type="button"
            onClick={() => onSelect(plan.id)}
            className={`w-full flex items-center justify-between p-4 rounded-xl border-2 transition-all text-left ${
              isSelected
                ? 'border-indigo-500 bg-indigo-50'
                : 'border-slate-200 bg-white hover:border-slate-300'
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                  isSelected
                    ? 'border-indigo-500 bg-indigo-500'
                    : 'border-slate-300'
                }`}
              >
                {isSelected && <Check className="w-3 h-3 text-white" />}
              </div>
              <span className={`text-sm font-semibold ${isSelected ? 'text-indigo-900' : 'text-slate-700'}`}>
                {plan.name}
              </span>
            </div>
            <span className={`text-sm font-bold ${isSelected ? 'text-indigo-600' : 'text-slate-500'}`}>
              {formatARS(plan.price)}
              <span className="text-xs font-normal text-slate-400">/mes</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
