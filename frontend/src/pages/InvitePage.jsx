import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CircularProgress } from '@mui/material';
import { Users, AlertTriangle, CheckCircle, Clock, ArrowLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getInvitation } from '../api/billing';
import RegistrationStep from '../components/onboarding/RegistrationStep';
import OnboardingForm from '../components/onboarding/OnboardingForm';
import PlanSelector from '../components/onboarding/PlanSelector';

function formatARS(amount) {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export default function InvitePage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();

  const [state, setState] = useState('loading'); // loading | invalid | expired | already_used | pending
  const [invite, setInvite] = useState(null);
  // Steps: 0 = invite details, 1 = registration, 2 = onboarding form
  const [step, setStep] = useState(0);
  const [selectedPlanId, setSelectedPlanId] = useState(null);

  useEffect(() => {
    if (authLoading) return;

    getInvitation(token)
      .then(({ data }) => {
        if (data.status === 'already_accepted') {
          if (user) {
            navigate('/dashboard', { replace: true });
          } else {
            setState('already_used');
          }
          return;
        }
        if (data.status === 'expired') {
          setState('expired');
          return;
        }
        if (data.status === 'pending') {
          setInvite(data);
          setState('pending');
        }
      })
      .catch(() => {
        setState('invalid');
      });
  }, [token, user, authLoading, navigate]);

  const handleContinue = () => {
    if (user) {
      // Already logged in, skip registration
      setStep(2);
    } else {
      setStep(1);
    }
  };

  const handleOnboardingComplete = (redirectUrl) => {
    if (redirectUrl) {
      navigate(redirectUrl, { replace: true });
    } else {
      navigate('/dashboard', { replace: true });
    }
  };

  if (authLoading || state === 'loading') {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <CircularProgress size={40} sx={{ color: '#6366f1' }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo / Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-indigo-600 mb-4">
            <Users className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Quantoryn</h1>
          <p className="text-slate-400 text-sm mt-1">Scientific Operating System</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {state === 'invalid' && (
            <div className="p-8 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-50 mb-4">
                <AlertTriangle className="w-7 h-7 text-red-500" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900 mb-2">Link no válido</h2>
              <p className="text-slate-500 text-sm">Este link de invitación no existe o fue eliminado.</p>
            </div>
          )}

          {state === 'expired' && (
            <div className="p-8 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-amber-50 mb-4">
                <Clock className="w-7 h-7 text-amber-500" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900 mb-2">Invitación expirada</h2>
              <p className="text-slate-500 text-sm">
                Esta invitación ya no es válida. Contacta a tu coach para recibir un nuevo link.
              </p>
            </div>
          )}

          {state === 'already_used' && (
            <div className="p-8 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-50 mb-4">
                <CheckCircle className="w-7 h-7 text-emerald-500" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900 mb-2">Invitación ya utilizada</h2>
              <p className="text-slate-500 text-sm">Esta invitación ya fue aceptada anteriormente.</p>
            </div>
          )}

          {state === 'pending' && invite && (
            <>
              {/* Header accent */}
              <div className="h-1.5 bg-gradient-to-r from-indigo-500 to-violet-500" />

              {/* Step 0: Invitation details */}
              {step === 0 && (
                <div className="p-6 sm:p-8">
                  <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-1">
                    Invitación de entrenamiento
                  </p>
                  <h2 className="text-2xl font-bold text-slate-900 mb-1">{invite.organization_name}</h2>
                  <p className="text-slate-500 text-sm mb-6">Te han invitado a unirte como atleta</p>

                  {/* Pre-assigned plan (single) */}
                  {invite.plan_name && (
                    <div className="bg-slate-50 rounded-xl p-5 mb-6 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-500">Plan</span>
                        <span className="text-sm font-semibold text-slate-900">{invite.plan_name}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-500">Precio mensual</span>
                        <span className="text-lg font-bold text-indigo-600">
                          {formatARS(invite.price)} <span className="text-xs font-normal text-slate-400">{invite.currency}</span>
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-slate-500">Válida hasta</span>
                        <span className="text-sm font-medium text-slate-700">{formatDate(invite.expires_at)}</span>
                      </div>
                    </div>
                  )}

                  {/* Athlete selects plan */}
                  {invite.plans && (
                    <div className="mb-6">
                      <PlanSelector
                        plans={invite.plans}
                        selectedPlanId={selectedPlanId}
                        onSelect={setSelectedPlanId}
                      />
                      <div className="flex items-center justify-between mt-3 text-sm text-slate-500">
                        <span>Válida hasta</span>
                        <span className="font-medium text-slate-700">{formatDate(invite.expires_at)}</span>
                      </div>
                    </div>
                  )}

                  <button
                    onClick={handleContinue}
                    disabled={invite.plans && !selectedPlanId}
                    className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
                  >
                    {user ? 'Completar mi perfil' : 'Continuar'}
                  </button>
                </div>
              )}

              {/* Step 1: Registration (only if not authenticated) */}
              {step === 1 && !user && (
                <>
                  <button
                    onClick={() => setStep(0)}
                    className="flex items-center gap-1 px-6 pt-4 text-sm text-slate-400 hover:text-slate-600 transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" /> Volver
                  </button>
                  <RegistrationStep onComplete={() => setStep(2)} />
                </>
              )}

              {/* Step 2: Onboarding form */}
              {step === 2 && (
                <>
                  <button
                    onClick={() => setStep(user ? 0 : 1)}
                    className="flex items-center gap-1 px-6 pt-4 text-sm text-slate-400 hover:text-slate-600 transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" /> Volver
                  </button>
                  <OnboardingForm
                    invitationToken={token}
                    invite={invite}
                    onComplete={handleOnboardingComplete}
                    selectedPlanId={selectedPlanId}
                    selectedPlanInfo={invite?.plans?.find(p => p.id === selectedPlanId)}
                  />
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-slate-500 mt-6">
          Al registrarte, aceptás los{' '}
          <a href="/terms" className="text-indigo-400 hover:text-indigo-300 underline">
            Términos de Servicio
          </a>{' '}
          y la{' '}
          <a href="/privacy" className="text-indigo-400 hover:text-indigo-300 underline">
            Política de Privacidad
          </a>
        </p>
      </div>
    </div>
  );
}
