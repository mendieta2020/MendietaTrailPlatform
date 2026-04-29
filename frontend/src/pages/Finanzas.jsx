import React, { useState, useEffect, useCallback } from 'react';
import {
  CircularProgress, Alert, Snackbar, Dialog, DialogTitle, DialogContent,
  DialogActions, Tooltip, Skeleton,
} from '@mui/material';
import {
  TrendingUp, Users, AlertTriangle, Plus, Copy, Check,
  DollarSign, RefreshCw, UserPlus, X, Link2, Shield, ExternalLink,
  Pencil, Trash2,
} from 'lucide-react';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { useSearchParams } from 'react-router-dom';
import {
  getBillingStatus,
  getCoachPricingPlans,
  createCoachPricingPlan,
  updateCoachPricingPlan,
  deleteCoachPricingPlan,
  getMPConnectUrl,
  disconnectMP,
  getInviteLink,
  regenerateInviteLink,
  createInvitation,
  getInvitations,
  getAthleteSubscriptions,
  activateAthleteManually,
  resendInvitation,
  syncAthleteSubscriptions,
  ownerSubscriptionAction,
} from '../api/billing';

// ── helpers ──────────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  active:    { label: 'Activo',    bg: 'bg-emerald-50',  text: 'text-emerald-700',  dot: 'bg-emerald-500' },
  pending:   { label: 'Pendiente', bg: 'bg-amber-50',    text: 'text-amber-700',    dot: 'bg-amber-400' },
  overdue:   { label: 'Atrasado',  bg: 'bg-red-50',      text: 'text-red-700',      dot: 'bg-red-500' },
  paused:    { label: 'Pausado',   bg: 'bg-amber-50',    text: 'text-amber-700',    dot: 'bg-amber-400' },
  cancelled: { label: 'Cancelado', bg: 'bg-slate-100',   text: 'text-slate-500',    dot: 'bg-slate-400' },
  suspended: { label: 'Suspendido',bg: 'bg-slate-100',   text: 'text-slate-500',    dot: 'bg-slate-400' },
};

const INV_STATUS_CONFIG = {
  pending:  { label: 'Pendiente', bg: 'bg-amber-50',  text: 'text-amber-700' },
  accepted: { label: 'Aceptada',  bg: 'bg-emerald-50',text: 'text-emerald-700' },
  rejected: { label: 'Rechazada', bg: 'bg-red-50',    text: 'text-red-700' },
  expired:  { label: 'Expirada',  bg: 'bg-slate-100', text: 'text-slate-500' },
};

function StatusBadge({ status, config }) {
  const cfg = config[status] || config.cancelled;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.dot && <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />}
      {cfg.label}
    </span>
  );
}

function formatARS(amount) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(amount);
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({ icon, label, value, subtext, accent }) {
  const IconEl = icon;
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
      <div className="flex items-start justify-between mb-3">
        <div className={`p-2.5 rounded-lg ${accent}`}>
          <IconEl className="w-5 h-5 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900 mb-0.5">{value}</p>
      <p className="text-sm font-medium text-slate-600">{label}</p>
      {subtext && <p className="text-xs text-slate-400 mt-1">{subtext}</p>}
    </div>
  );
}

// ── Modal Nuevo Plan ──────────────────────────────────────────────────────────

function NewPlanModal({ open, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [priceArs, setPriceArs] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleClose = () => {
    setName(''); setPriceArs(''); setDescription(''); setError('');
    onClose();
  };

  const handleSubmit = async () => {
    if (!name.trim() || !priceArs) { setError('Nombre y precio son requeridos.'); return; }
    setLoading(true); setError('');
    try {
      const res = await createCoachPricingPlan({ name: name.trim(), price_ars: priceArs, description });
      onCreated(res.data);
      handleClose();
    } catch {
      setError('No se pudo crear el plan. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth
      PaperProps={{ className: 'rounded-2xl shadow-xl' }}>
      <DialogTitle className="pb-2">
        <span className="text-lg font-semibold text-slate-900">Nuevo plan de precios</span>
      </DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" onClose={() => setError('')} className="mb-4 rounded-lg">
            {error}
          </Alert>
        )}
        <div className="flex flex-col gap-4 pt-2">
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Nombre del plan *</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="ej: Programa Online Elite"
              className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Precio mensual (ARS) *</label>
            <input
              type="number"
              value={priceArs}
              onChange={e => setPriceArs(e.target.value)}
              placeholder="ej: 15000"
              className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Descripción (opcional)</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
              placeholder="¿Qué incluye este plan?"
              className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 resize-none"
            />
          </div>
        </div>
      </DialogContent>
      <DialogActions className="px-6 pb-5 gap-2">
        <button onClick={handleClose} disabled={loading}
          className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
          Cancelar
        </button>
        <button onClick={handleSubmit} disabled={loading}
          className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60">
          {loading && <CircularProgress size={14} color="inherit" />}
          {loading ? 'Guardando…' : 'Crear plan'}
        </button>
      </DialogActions>
    </Dialog>
  );
}

// ── Modal Invitar Atleta ──────────────────────────────────────────────────────

function InviteAthleteModal({ open, onClose, plans, onInvited }) {
  const [selectedPlan, setSelectedPlan] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [inviteUrl, setInviteUrl] = useState('');
  const [copied, setCopied] = useState(false);

  const handleClose = () => {
    setSelectedPlan(''); setEmail(''); setError(''); setInviteUrl(''); setCopied(false);
    onClose();
  };

  const handleSubmit = async () => {
    if (!selectedPlan || !email) { setError('Seleccioná un plan e ingresá un email.'); return; }
    setLoading(true); setError('');
    try {
      const res = await createInvitation(Number(selectedPlan), email);
      setInviteUrl(res.data.invite_url);
      onInvited();
    } catch {
      setError('No se pudo crear la invitación. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth
      PaperProps={{ className: 'rounded-2xl shadow-xl' }}>
      <DialogTitle className="pb-2">
        <span className="text-lg font-semibold text-slate-900">Invitar atleta</span>
      </DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" onClose={() => setError('')} className="mb-4 rounded-lg">{error}</Alert>
        )}
        {inviteUrl ? (
          <div className="pt-2">
            <Alert severity="success" className="mb-4 rounded-lg">
              Invitación creada. Enviá este link al atleta para que se registre y pague.
            </Alert>
            <div className="flex items-center gap-2 p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <p className="text-xs text-slate-600 flex-1 break-all font-mono">{inviteUrl}</p>
              <button onClick={handleCopy}
                className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors">
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copiado' : 'Copiar'}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 pt-2">
            <div>
              <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Plan *</label>
              <select
                value={selectedPlan}
                onChange={e => setSelectedPlan(e.target.value)}
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 bg-white">
                <option value="">Seleccionar plan…</option>
                {plans.filter(p => p.is_active).map(p => (
                  <option key={p.id} value={p.id}>{p.name} — {formatARS(p.price_ars)}/mes</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Email del atleta *</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="atleta@ejemplo.com"
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
              />
            </div>
          </div>
        )}
      </DialogContent>
      <DialogActions className="px-6 pb-5 gap-2">
        <button onClick={handleClose}
          className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
          {inviteUrl ? 'Cerrar' : 'Cancelar'}
        </button>
        {!inviteUrl && (
          <button onClick={handleSubmit} disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60">
            {loading && <CircularProgress size={14} color="inherit" />}
            {loading ? 'Creando…' : 'Crear invitación'}
          </button>
        )}
      </DialogActions>
    </Dialog>
  );
}

// ── Modal Activación Manual ────────────────────────────────────────────────────

function ActivateManualModal({ open, subscription, onClose, onActivated }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleConfirm = async () => {
    setLoading(true); setError('');
    try {
      await activateAthleteManually(subscription.id);
      onActivated(subscription.id);
      onClose();
    } catch {
      setError('No se pudo activar la suscripción. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth
      PaperProps={{ className: 'rounded-2xl shadow-xl' }}>
      <DialogTitle>
        <span className="text-lg font-semibold text-slate-900">Activar sin pago MP</span>
      </DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" className="mb-3 rounded-lg">{error}</Alert>}
        <p className="text-sm text-slate-600">
          Activar <strong>{subscription?.athlete_first_name} {subscription?.athlete_last_name}</strong> manualmente
          indica que el pago se realizó por <strong>efectivo o transferencia</strong>, fuera de MercadoPago.
        </p>
        <p className="text-xs text-slate-400 mt-2">Esta acción queda registrada en el historial.</p>
      </DialogContent>
      <DialogActions className="px-6 pb-5 gap-2">
        <button onClick={onClose} disabled={loading}
          className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
          Cancelar
        </button>
        <button onClick={handleConfirm} disabled={loading}
          className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60">
          {loading && <CircularProgress size={14} color="inherit" />}
          {loading ? 'Activando…' : 'Confirmar activación'}
        </button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const Finanzas = () => {
  const { activeOrg, orgLoading } = useOrg();
  const [searchParams, setSearchParams] = useSearchParams();

  const [billingStatus, setBillingStatus] = useState(null);
  const [plans, setPlans] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [inviteLink, setInviteLink] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [newPlanOpen, setNewPlanOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [activateTarget, setActivateTarget] = useState(null);

  const [subFilter, setSubFilter] = useState('all');
  const [resendingToken, setResendingToken] = useState(null);
  const [editingPlan, setEditingPlan] = useState(null);
  const [mpConnecting, setMpConnecting] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const showToast = (message, severity = 'success') => setToast({ open: true, message, severity });

  // PR-150: Check for MP callback success
  useEffect(() => {
    if (searchParams.get('mp_connected') === 'true') {
      showToast('MercadoPago conectado exitosamente.');
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const loadData = useCallback(async () => {
    if (!activeOrg) return;
    setLoading(true); setError('');
    try {
      const [statusRes, plansRes, subsRes, invRes, linkRes] = await Promise.all([
        getBillingStatus().catch(() => ({ data: null })),
        getCoachPricingPlans().catch(() => ({ data: [] })),
        getAthleteSubscriptions().catch(() => ({ data: [] })),
        getInvitations().catch(() => ({ data: [] })),
        getInviteLink().catch(() => ({ data: null })),
      ]);
      if (statusRes.data) setBillingStatus(statusRes.data);
      setPlans(Array.isArray(plansRes.data) ? plansRes.data : []);
      setSubscriptions(Array.isArray(subsRes.data) ? subsRes.data : []);
      setInvitations(Array.isArray(invRes.data) ? invRes.data : []);
      if (linkRes.data) setInviteLink(linkRes.data);
    } catch {
      setError('No se pudieron cargar los datos de facturación.');
    } finally {
      setLoading(false);
    }
  }, [activeOrg]);

  useEffect(() => { loadData(); }, [loadData]);

  // PR-150: MP Connect handler
  const handleMPConnect = async () => {
    setMpConnecting(true);
    try {
      const { data } = await getMPConnectUrl();
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch {
      showToast('Error al conectar MercadoPago.', 'error');
      setMpConnecting(false);
    }
  };

  // PR-150: MP Disconnect handler
  const handleMPDisconnect = async () => {
    try {
      await disconnectMP();
      setBillingStatus(prev => prev ? { ...prev, mp_connected: false } : prev);
      showToast('MercadoPago desconectado.');
    } catch {
      showToast('Error al desconectar.', 'error');
    }
  };

  // PR-150: Copy invite link
  const handleCopyLink = () => {
    if (inviteLink?.url) {
      navigator.clipboard.writeText(inviteLink.url);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    }
  };

  // PR-150: Regenerate invite link
  const handleRegenerateLink = async () => {
    setRegenerating(true);
    try {
      const { data } = await regenerateInviteLink();
      setInviteLink(data);
      showToast('Link regenerado. El anterior ya no funciona.');
    } catch {
      showToast('Error al regenerar el link.', 'error');
    } finally {
      setRegenerating(false);
    }
  };

  // PR-151: Plan edit/delete handlers
  const handleUpdatePlan = async (plan) => {
    try {
      const { data } = await updateCoachPricingPlan(plan.id, plan);
      setPlans(prev => prev.map(p => p.id === data.id ? { ...p, ...data } : p));
      setEditingPlan(null);
      showToast('Plan actualizado.');
    } catch {
      showToast('Error al actualizar el plan.', 'error');
    }
  };

  const handleDeletePlan = async (planId) => {
    if (!window.confirm('¿Desactivar este plan? Los atletas suscritos no se verán afectados.')) return;
    try {
      await deleteCoachPricingPlan(planId);
      setPlans(prev => prev.filter(p => p.id !== planId));
      showToast('Plan desactivado.');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      showToast(detail || 'Error al desactivar el plan.', 'error');
    }
  };

  // ── KPI calculations ──────────────────────────────────────────────────────
  const now = new Date();
  const activeSubscriptions = subscriptions.filter(s => s.status === 'active');
  const overdueSubscriptions = subscriptions.filter(s => s.status === 'overdue');
  const trialSubscriptions = subscriptions.filter(
    s => s.trial_ends_at && new Date(s.trial_ends_at) > now && s.status !== 'active',
  );
  const monthlyRevenue = activeSubscriptions.reduce((sum, s) => sum + parseFloat(s.price_ars || 0), 0);
  const overdueRevenue = overdueSubscriptions.reduce((sum, s) => sum + parseFloat(s.price_ars || 0), 0);

  // ── Filtered subscriptions ────────────────────────────────────────────────
  const filteredSubs = subFilter === 'all' ? subscriptions
    : subFilter === 'trial'
      ? trialSubscriptions
      : subscriptions.filter(s => s.status === subFilter);

  const handleActivated = (subId) => {
    setSubscriptions(prev => prev.map(s => s.id === subId ? { ...s, status: 'active' } : s));
    showToast('Atleta activado correctamente.');
  };

  const handlePlanCreated = (plan) => {
    setPlans(prev => [...prev, plan]);
    showToast('Plan creado correctamente.');
  };

  const handleResend = async (token) => {
    setResendingToken(token);
    try {
      await resendInvitation(token);
      await loadData();
      showToast('Invitación reenviada con nuevo link.');
    } catch {
      showToast('No se pudo reenviar la invitación.', 'error');
    } finally {
      setResendingToken(null);
    }
  };

  const handleOwnerAction = async (subId, action) => {
    try {
      await ownerSubscriptionAction(subId, action, 'owner_decision', '');
      await loadData();
      const msgs = { pause: 'Suscripción pausada.', cancel: 'Suscripción cancelada.', reactivate: 'Suscripción reactivada.' };
      showToast(msgs[action] || 'Listo.');
    } catch {
      showToast('No se pudo realizar la acción. Intenta de nuevo.', 'error');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await syncAthleteSubscriptions();
      const count = res.data?.reconciled?.length ?? 0;
      showToast(`${count} suscripción${count !== 1 ? 'es' : ''} actualizada${count !== 1 ? 's' : ''}.`);
      await loadData();
    } catch {
      showToast('No se pudo sincronizar con MercadoPago.', 'error');
    } finally {
      setSyncing(false);
    }
  };

  // ── Guard: role check (owner/admin) ───────────────────────────────────────
  const userRole = activeOrg?.role;
  const isAdminOrOwner = userRole === 'owner' || userRole === 'admin';

  if (orgLoading) {
    return (
      <Layout>
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[1, 2, 3].map(i => <Skeleton key={i} variant="rounded" height={120} />)}
          </div>
          <Skeleton variant="rounded" height={300} />
        </div>
      </Layout>
    );
  }

  if (!activeOrg) {
    return (
      <Layout>
        <Alert severity="info" className="m-4 rounded-xl">Sin organización asignada.</Alert>
      </Layout>
    );
  }

  if (!isAdminOrOwner) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <DollarSign className="w-12 h-12 text-slate-300 mb-4" />
          <h3 className="text-lg font-semibold text-slate-700">Acceso restringido</h3>
          <p className="text-sm text-slate-500 mt-1">Esta sección es exclusiva para administradores de la organización.</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Finanzas</h1>
          <p className="text-sm text-slate-500 mt-0.5">Estado financiero y gestión de suscripciones.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-3 py-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 transition-colors disabled:opacity-50"
          >
            {syncing ? <CircularProgress size={14} /> : <RefreshCw className="w-4 h-4" />}
            Sincronizar con MercadoPago
          </button>
          <button onClick={loadData}
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">
            <RefreshCw className="w-4 h-4" />
            Actualizar
          </button>
        </div>
      </div>

      {error && (
        <Alert severity="error" onClose={() => setError('')} className="mb-5 rounded-xl">{error}</Alert>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[1, 2, 3].map(i => <Skeleton key={i} variant="rounded" height={120} />)}
          </div>
          <Skeleton variant="rounded" height={300} />
          <Skeleton variant="rounded" height={400} />
        </div>
      ) : (
        <div className="space-y-8">

          {/* ── PR-150: MP Connect Banner ───────────────────────────────── */}
          {billingStatus && !billingStatus.mp_connected && (
            <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-amber-100 rounded-xl">
                  <Shield className="w-6 h-6 text-amber-600" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-amber-900">Conectá tu MercadoPago</h3>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Para cobrar a tus atletas, necesitás conectar tu cuenta de MercadoPago.
                  </p>
                </div>
              </div>
              <button
                onClick={handleMPConnect}
                disabled={mpConnecting}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-60 shrink-0"
              >
                {mpConnecting ? <CircularProgress size={16} sx={{ color: 'white' }} /> : <ExternalLink className="w-4 h-4" />}
                Conectar MercadoPago
              </button>
            </div>
          )}

          {billingStatus?.mp_connected && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-sm font-medium text-emerald-800">MercadoPago conectado</span>
              </div>
              <button
                onClick={handleMPDisconnect}
                className="text-xs text-slate-500 hover:text-red-600 transition-colors"
              >
                Desconectar
              </button>
            </div>
          )}

          {/* ── PR-150: Link de Equipo ──────────────────────────────────── */}
          {inviteLink && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <Link2 className="w-5 h-5 text-indigo-500" />
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">Link de equipo</h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Compartí este link en WhatsApp para que tus atletas se registren
                    </p>
                  </div>
                </div>
              </div>
              <div className="px-6 py-4 flex items-center gap-3">
                <div className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <p className="text-sm text-slate-700 font-mono break-all">{inviteLink.url}</p>
                </div>
                <button
                  onClick={handleCopyLink}
                  className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors shrink-0"
                >
                  {linkCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {linkCopied ? 'Copiado' : 'Copiar'}
                </button>
                <button
                  onClick={handleRegenerateLink}
                  disabled={regenerating}
                  className="flex items-center gap-2 px-3 py-2.5 text-sm text-slate-500 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors shrink-0 disabled:opacity-60"
                >
                  <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>
          )}

          {/* ── PR-150: Atención Requerida (overdue) ───────────────────── */}
          {overdueSubscriptions.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-3">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                <h3 className="text-sm font-bold text-red-900">
                  Atención requerida — {overdueSubscriptions.length} pago{overdueSubscriptions.length > 1 ? 's' : ''} atrasado{overdueSubscriptions.length > 1 ? 's' : ''}
                </h3>
              </div>
              <div className="space-y-2">
                {overdueSubscriptions.slice(0, 5).map(sub => (
                  <div key={sub.id} className="flex items-center justify-between bg-white rounded-lg px-4 py-2 border border-red-100">
                    <span className="text-sm font-medium text-slate-900">
                      {sub.athlete_first_name} {sub.athlete_last_name}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-slate-500">{sub.coach_plan_name}</span>
                      <span className="text-sm font-bold text-red-600">{formatARS(sub.price_ars)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── SECCIÓN 1: KPIs ─────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
            <KpiCard
              icon={TrendingUp}
              label="Ingresos del mes"
              value={formatARS(monthlyRevenue)}
              subtext={`${activeSubscriptions.length} suscripciones activas`}
              accent="bg-emerald-500"
            />
            <KpiCard
              icon={Users}
              label="Atletas activos"
              value={activeSubscriptions.length}
              subtext={billingStatus ? `Plan ${billingStatus.plan_display}` : undefined}
              accent="bg-blue-500"
            />
            <KpiCard
              icon={AlertTriangle}
              label="Pagos atrasados"
              value={overdueSubscriptions.length}
              subtext={overdueSubscriptions.length > 0 ? `${formatARS(overdueRevenue)} pendiente` : 'Sin atrasos'}
              accent={overdueSubscriptions.length > 0 ? 'bg-red-500' : 'bg-slate-400'}
            />
            <KpiCard
              icon={AlertTriangle}
              label="En trial"
              value={trialSubscriptions.length}
              subtext={trialSubscriptions.length > 0 ? 'Período de prueba activo' : 'Sin trials activos'}
              accent={trialSubscriptions.length > 0 ? 'bg-amber-400' : 'bg-slate-400'}
            />
          </div>

          {/* ── SECCIÓN 2: Planes de precios ─────────────────────────────── */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Planes de precios</h2>
                <p className="text-xs text-slate-500 mt-0.5">Planes que ofrecés a tus atletas.</p>
              </div>
              <button onClick={() => setNewPlanOpen(true)}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors">
                <Plus className="w-4 h-4" />
                Nuevo plan
              </button>
            </div>
            {plans.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14 text-center">
                <DollarSign className="w-10 h-10 text-slate-300 mb-3" />
                <p className="text-sm font-medium text-slate-600">Sin planes configurados</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">Crea un plan para poder invitar atletas.</p>
                <button onClick={() => setNewPlanOpen(true)}
                  className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors">
                  Crear primer plan
                </button>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {plans.map(plan => (
                  <div key={plan.id} className="flex items-center justify-between px-6 py-4">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{plan.name}</p>
                      {plan.description && (
                        <p className="text-xs text-slate-500 mt-0.5">{plan.description}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-4">
                      <p className="text-sm font-bold text-slate-900">{formatARS(plan.price_ars)}<span className="text-xs font-normal text-slate-400">/mes</span></p>
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${plan.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                        {plan.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                      <button onClick={() => setEditingPlan(plan)} className="p-1.5 text-slate-400 hover:text-indigo-600 rounded-lg hover:bg-slate-100 transition-colors">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleDeletePlan(plan.id)} className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── SECCIÓN 3: Lista de atletas ──────────────────────────────── */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Suscripciones de atletas</h2>
                <p className="text-xs text-slate-500 mt-0.5">{subscriptions.length} total</p>
              </div>
              {/* Filter tabs */}
              <div className="flex items-center bg-slate-100 rounded-lg p-1 gap-0.5">
                {[
                  { key: 'all', label: `Todos (${subscriptions.length})` },
                  { key: 'active', label: `Activos (${activeSubscriptions.length})` },
                  { key: 'overdue', label: `Vencidos (${overdueSubscriptions.length})` },
                  { key: 'paused', label: `Pausados (${subscriptions.filter(s => s.status === 'paused').length})` },
                  { key: 'trial', label: `Trial (${trialSubscriptions.length})` },
                ].map(({ key, label }) => (
                  <button key={key} onClick={() => setSubFilter(key)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${subFilter === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {filteredSubs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14 text-center">
                <Users className="w-10 h-10 text-slate-300 mb-3" />
                <p className="text-sm font-medium text-slate-600">Sin resultados</p>
                <p className="text-xs text-slate-400 mt-1">No hay atletas en este estado.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-50">
                      <th className="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Atleta</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Plan</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Estado</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Motivo</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Monto</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Próximo pago</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSubs.map(sub => {
                      const isOverdue = sub.status === 'overdue';
                      const isTrial = sub.trial_ends_at && new Date(sub.trial_ends_at) > now && sub.status !== 'active';
                      const overdueDays = isOverdue && sub.next_payment_at
                        ? Math.max(0, Math.floor((now - new Date(sub.next_payment_at)) / 86400000))
                        : 0;
                      const trialDaysLeft = isTrial
                        ? Math.max(0, Math.ceil((new Date(sub.trial_ends_at) - now) / 86400000))
                        : 0;

                      const rowBg = isOverdue ? 'bg-red-50' : isTrial ? 'bg-amber-50' : '';
                      const whatsappName = encodeURIComponent(`${sub.athlete_first_name || ''} ${sub.athlete_last_name || ''}`.trim());
                      const whatsappPlan = encodeURIComponent(sub.coach_plan_name || 'tu plan');
                      const whatsappMsg = `Hola%20${whatsappName},%20tu%20cuota%20de%20${whatsappPlan}%20está%20pendiente.%20¿Podés%20regularizarla?`;

                      return (
                        <tr key={sub.id} className={`hover:brightness-95 transition-colors ${rowBg}`}>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-700">
                                {(sub.athlete_first_name || '?').charAt(0)}{(sub.athlete_last_name || '').charAt(0)}
                              </div>
                              <div>
                                <p className="text-sm font-semibold text-slate-900">{sub.athlete_first_name} {sub.athlete_last_name}</p>
                                <p className="text-xs text-slate-400">{sub.athlete_email}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-4">
                            <p className="text-sm text-slate-700">{sub.coach_plan_name}</p>
                          </td>
                          <td className="px-4 py-4">
                            <div className="flex flex-col gap-0.5">
                              <StatusBadge status={sub.status} config={STATUS_CONFIG} />
                              {isOverdue && overdueDays > 0 && (
                                <span className="text-xs text-red-600 font-medium">Vencido ({overdueDays}d)</span>
                              )}
                              {isTrial && (
                                <span className="text-xs text-amber-600 font-medium">Trial ({trialDaysLeft}d)</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-4">
                            {(sub.pause_reason || sub.cancellation_reason) ? (
                              <p className="text-xs text-slate-500 max-w-[120px] truncate" title={sub.pause_reason || sub.cancellation_reason}>
                                {sub.pause_reason || sub.cancellation_reason}
                              </p>
                            ) : (
                              <p className="text-xs text-slate-300">—</p>
                            )}
                          </td>
                          <td className="px-4 py-4">
                            <p className="text-sm font-semibold text-slate-900">{formatARS(sub.price_ars)}</p>
                          </td>
                          <td className="px-4 py-4">
                            <p className="text-sm text-slate-500">{formatDate(sub.next_payment_at)}</p>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {isOverdue && (
                                sub.athlete_phone ? (
                                  <Tooltip title="Enviar recordatorio por WhatsApp">
                                    <a
                                      href={`https://wa.me/${sub.athlete_phone.replace(/\D/g, '')}?text=${whatsappMsg}`}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                                      Recordar
                                    </a>
                                  </Tooltip>
                                ) : (
                                  <Tooltip title="Sin teléfono registrado">
                                    <span className="px-3 py-1.5 text-xs font-medium text-slate-400 bg-slate-100 rounded-lg cursor-not-allowed">
                                      Recordar
                                    </span>
                                  </Tooltip>
                                )
                              )}
                              {(sub.status === 'pending' || sub.status === 'overdue') && (
                                <Tooltip title="Activar sin pago MercadoPago (efectivo/transferencia)">
                                  <button onClick={() => setActivateTarget(sub)}
                                    className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                                    Activar manualmente
                                  </button>
                                </Tooltip>
                              )}
                              {sub.status === 'active' && (
                                <Tooltip title="Pausar suscripción">
                                  <button onClick={() => handleOwnerAction(sub.id, 'pause')}
                                    className="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors">
                                    Pausar
                                  </button>
                                </Tooltip>
                              )}
                              {(sub.status === 'active' || sub.status === 'paused') && (
                                <Tooltip title="Cancelar suscripción">
                                  <button onClick={() => handleOwnerAction(sub.id, 'cancel')}
                                    className="px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 hover:bg-red-100 rounded-lg transition-colors">
                                    Cancelar
                                  </button>
                                </Tooltip>
                              )}
                              {(sub.status === 'paused' || sub.status === 'cancelled') && (
                                <Tooltip title="Reactivar suscripción">
                                  <button onClick={() => handleOwnerAction(sub.id, 'reactivate')}
                                    className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                                    Reactivar
                                  </button>
                                </Tooltip>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── SECCIÓN 4: Invitaciones ───────────────────────────────────── */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Invitaciones</h2>
                <p className="text-xs text-slate-500 mt-0.5">Links de registro enviados a atletas.</p>
              </div>
              <button onClick={() => setInviteOpen(true)}
                disabled={plans.filter(p => p.is_active).length === 0}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                <UserPlus className="w-4 h-4" />
                Invitar atleta
              </button>
            </div>
            {invitations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14 text-center">
                <UserPlus className="w-10 h-10 text-slate-300 mb-3" />
                <p className="text-sm font-medium text-slate-600">Sin invitaciones aún</p>
                <p className="text-xs text-slate-400 mt-1 mb-4">Invitá atletas para que se registren y paguen.</p>
                <button
                  onClick={() => setInviteOpen(true)}
                  disabled={plans.filter(p => p.is_active).length === 0}
                  className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors disabled:opacity-50">
                  Crear primera invitación
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-slate-50">
                      <th className="text-left px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Email</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Plan</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Estado</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Expira</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {invitations.map(inv => (
                      <tr key={inv.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4">
                          <p className="text-sm text-slate-900">{inv.email}</p>
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm text-slate-700">{inv.coach_plan_name}</p>
                        </td>
                        <td className="px-4 py-4">
                          <StatusBadge status={inv.status} config={INV_STATUS_CONFIG} />
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm text-slate-500">{formatDate(inv.expires_at)}</p>
                        </td>
                        <td className="px-6 py-4 text-right">
                          {inv.status === 'pending' && (
                            <button
                              onClick={() => handleResend(inv.token)}
                              disabled={resendingToken === inv.token}
                              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-60 ml-auto">
                              {resendingToken === inv.token
                                ? <CircularProgress size={12} />
                                : <RefreshCw className="w-3.5 h-3.5" />}
                              Reenviar
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modales */}
      <NewPlanModal
        open={newPlanOpen}
        onClose={() => setNewPlanOpen(false)}
        onCreated={handlePlanCreated}
      />
      <InviteAthleteModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        plans={plans}
        onInvited={() => { loadData(); }}
      />
      {activateTarget && (
        <ActivateManualModal
          open={Boolean(activateTarget)}
          subscription={activateTarget}
          onClose={() => setActivateTarget(null)}
          onActivated={handleActivated}
        />
      )}

      {/* PR-151: Edit Plan Modal */}
      {editingPlan && (
        <Dialog open={Boolean(editingPlan)} onClose={() => setEditingPlan(null)} maxWidth="sm" fullWidth PaperProps={{ className: 'rounded-2xl shadow-xl' }}>
          <DialogTitle><span className="text-lg font-semibold text-slate-900">Editar plan</span></DialogTitle>
          <DialogContent>
            <div className="flex flex-col gap-4 pt-2">
              <div>
                <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Nombre del plan *</label>
                <input type="text" value={editingPlan.name} onChange={e => setEditingPlan({ ...editingPlan, name: e.target.value })}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
              </div>
              <div>
                <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Precio mensual (ARS) *</label>
                <input type="number" value={editingPlan.price_ars} onChange={e => setEditingPlan({ ...editingPlan, price_ars: e.target.value })}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500" />
              </div>
              <div>
                <label className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1 block">Descripción</label>
                <textarea value={editingPlan.description || ''} onChange={e => setEditingPlan({ ...editingPlan, description: e.target.value })} rows={2}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none" />
              </div>
              <div className="flex items-center justify-between px-1">
                <div>
                  <p className="text-sm font-medium text-slate-700">Estado del plan</p>
                  <p className="text-xs text-slate-400">Los atletas solo ven planes activos</p>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingPlan({ ...editingPlan, is_active: !editingPlan.is_active })}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${editingPlan.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}
                >
                  <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${editingPlan.is_active ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
            </div>
          </DialogContent>
          <DialogActions className="px-6 pb-5 gap-2">
            <button onClick={() => setEditingPlan(null)} className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">Cancelar</button>
            <button onClick={() => handleUpdatePlan(editingPlan)} className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors">Guardar</button>
          </DialogActions>
        </Dialog>
      )}

      {/* Toast */}
      <Snackbar
        open={toast.open}
        autoHideDuration={3000}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert severity={toast.severity} onClose={() => setToast(t => ({ ...t, open: false }))}
          className="rounded-xl shadow-lg">
          {toast.message}
        </Alert>
      </Snackbar>
    </Layout>
  );
};

export default Finanzas;
