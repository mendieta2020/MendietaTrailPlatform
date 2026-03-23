import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CircularProgress } from '@mui/material';
import { Users, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getInvitation, acceptInvitation } from '../api/billing';

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
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState(null);

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
      .catch((err) => {
        if (err?.response?.status === 404) {
          setState('invalid');
        } else {
          setState('invalid');
        }
      });
  }, [token, user, authLoading, navigate]);

  async function handleAccept() {
    if (!user) {
      navigate(`/login?next=/invite/${token}`);
      return;
    }

    setAccepting(true);
    setError(null);

    try {
      const { data } = await acceptInvitation(token);
      if (data.already_member) {
        navigate('/dashboard', { replace: true });
        return;
      }
      if (data.redirect_url) {
        window.location.href = data.redirect_url;
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Ocurrió un error. Intenta nuevamente.';
      setError(msg);
    } finally {
      setAccepting(false);
    }
  }

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

              <div className="p-8">
                <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-1">
                  Invitación de entrenamiento
                </p>
                <h2 className="text-2xl font-bold text-slate-900 mb-1">{invite.organization_name}</h2>
                <p className="text-slate-500 text-sm mb-6">Te han invitado a unirte como atleta</p>

                {/* Plan details */}
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

                {error && (
                  <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-100 text-sm text-red-700">
                    {error}
                  </div>
                )}

                <button
                  onClick={handleAccept}
                  disabled={accepting}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
                >
                  {accepting ? (
                    <CircularProgress size={18} sx={{ color: 'white' }} />
                  ) : (
                    'Unirme y pagar'
                  )}
                </button>

                {!user && (
                  <p className="text-center text-xs text-slate-400 mt-3">
                    Necesitás una cuenta Quantoryn para continuar
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
