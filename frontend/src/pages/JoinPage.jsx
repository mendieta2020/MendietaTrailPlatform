import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CircularProgress } from '@mui/material';
import { Users, AlertTriangle, ArrowLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getJoinDetail } from '../api/billing';
import RegistrationStep from '../components/onboarding/RegistrationStep';
import OnboardingForm from '../components/onboarding/OnboardingForm';
import PlanSelector from '../components/onboarding/PlanSelector';

export default function JoinPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();

  const [state, setState] = useState('loading'); // loading | invalid | ready
  const [orgData, setOrgData] = useState(null);
  const [step, setStep] = useState(0);
  const [selectedPlanId, setSelectedPlanId] = useState(null);

  useEffect(() => {
    if (authLoading) return;

    getJoinDetail(slug)
      .then(({ data }) => {
        setOrgData(data);
        setState('ready');
      })
      .catch(() => {
        setState('invalid');
      });
  }, [slug, authLoading]);

  const handleContinue = () => {
    if (user) {
      setStep(2);
    } else {
      setStep(1);
    }
  };

  const handleOnboardingComplete = (redirectUrl) => {
    if (redirectUrl) {
      if (redirectUrl.startsWith('http')) {
        window.location.href = redirectUrl;
      } else {
        navigate(redirectUrl, { replace: true });
      }
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
        {/* Logo */}
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
              <p className="text-slate-500 text-sm">Este link de equipo no existe o fue desactivado.</p>
            </div>
          )}

          {state === 'ready' && orgData && (
            <>
              <div className="h-1.5 bg-gradient-to-r from-indigo-500 to-violet-500" />

              {/* Step 0: Plan selection */}
              {step === 0 && (
                <div className="p-6 sm:p-8">
                  <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-1">
                    Unite al equipo
                  </p>
                  <h2 className="text-2xl font-bold text-slate-900 mb-1">{orgData.organization_name}</h2>
                  <p className="text-slate-500 text-sm mb-6">Elegí tu plan y empezá a entrenar</p>

                  <div className="mb-6">
                    <PlanSelector
                      plans={orgData.plans}
                      selectedPlanId={selectedPlanId}
                      onSelect={setSelectedPlanId}
                    />
                  </div>

                  <button
                    onClick={handleContinue}
                    disabled={!selectedPlanId}
                    className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
                  >
                    {user ? 'Completar mi perfil' : 'Continuar'}
                  </button>
                </div>
              )}

              {/* Step 1: Registration */}
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
                    joinSlug={slug}
                    invite={null}
                    onComplete={handleOnboardingComplete}
                    selectedPlanId={selectedPlanId}
                    selectedPlanInfo={orgData?.plans?.find(p => p.id === selectedPlanId)}
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
