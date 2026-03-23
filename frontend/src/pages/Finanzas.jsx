import React, { useState, useEffect, useCallback } from 'react';
import {
  CircularProgress, Alert, Snackbar, Dialog, DialogTitle, DialogContent,
  DialogActions, Tooltip, Skeleton,
} from '@mui/material';
import {
  TrendingUp, Users, AlertTriangle, Plus, Copy, Check,
  DollarSign, RefreshCw, UserPlus, X,
} from 'lucide-react';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import {
  getBillingStatus,
  getCoachPricingPlans,
  createCoachPricingPlan,
  createInvitation,
  getInvitations,
  getAthleteSubscriptions,
  activateAthleteManually,
  resendInvitation,
} from '../api/billing';

// ── helpers ──────────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  active:    { label: 'Activo',    bg: 'bg-emerald-50',  text: 'text-emerald-700',  dot: 'bg-emerald-500' },
  pending:   { label: 'Pendiente', bg: 'bg-amber-50',    text: 'text-amber-700',    dot: 'bg-amber-400' },
  overdue:   { label: 'Atrasado',  bg: 'bg-red-50',      text: 'text-red-700',      dot: 'bg-red-500' },
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

  const [billingStatus, setBillingStatus] = useState(null);
  const [plans, setPlans] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [newPlanOpen, setNewPlanOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [activateTarget, setActivateTarget] = useState(null);

  const [subFilter, setSubFilter] = useState('all');
  const [resendingToken, setResendingToken] = useState(null);

  const showToast = (message, severity = 'success') => setToast({ open: true, message, severity });

  const loadData = useCallback(async () => {
    if (!activeOrg) return;
    setLoading(true); setError('');
    try {
      const [statusRes, plansRes, subsRes, invRes] = await Promise.all([
        getBillingStatus(),
        getCoachPricingPlans(),
        getAthleteSubscriptions(),
        getInvitations(),
      ]);
      setBillingStatus(statusRes.data);
      setPlans(plansRes.data);
      setSubscriptions(subsRes.data);
      setInvitations(invRes.data);
    } catch {
      setError('No se pudieron cargar los datos de facturación.');
    } finally {
      setLoading(false);
    }
  }, [activeOrg]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── KPI calculations ──────────────────────────────────────────────────────
  const activeSubscriptions = subscriptions.filter(s => s.status === 'active');
  const overdueSubscriptions = subscriptions.filter(s => s.status === 'overdue');
  const monthlyRevenue = activeSubscriptions.reduce((sum, s) => sum + parseFloat(s.price_ars || 0), 0);
  const overdueRevenue = overdueSubscriptions.reduce((sum, s) => sum + parseFloat(s.price_ars || 0), 0);

  // ── Filtered subscriptions ────────────────────────────────────────────────
  const filteredSubs = subFilter === 'all' ? subscriptions
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
        <button onClick={loadData}
          className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">
          <RefreshCw className="w-4 h-4" />
          Actualizar
        </button>
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

          {/* ── SECCIÓN 1: KPIs ─────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
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
                  { key: 'all', label: 'Todos' },
                  { key: 'active', label: 'Activos' },
                  { key: 'pending', label: 'Pendientes' },
                  { key: 'overdue', label: 'Atrasados' },
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
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Monto</th>
                      <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Próximo pago</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSubs.map(sub => (
                      <tr key={sub.id} className="hover:bg-slate-50 transition-colors">
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
                          <StatusBadge status={sub.status} config={STATUS_CONFIG} />
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm font-semibold text-slate-900">{formatARS(sub.price_ars)}</p>
                        </td>
                        <td className="px-4 py-4">
                          <p className="text-sm text-slate-500">{formatDate(sub.next_payment_at)}</p>
                        </td>
                        <td className="px-6 py-4 text-right">
                          {(sub.status === 'pending' || sub.status === 'overdue') && (
                            <Tooltip title="Activar sin pago MercadoPago (efectivo/transferencia)">
                              <button onClick={() => setActivateTarget(sub)}
                                className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                                Activar manualmente
                              </button>
                            </Tooltip>
                          )}
                        </td>
                      </tr>
                    ))}
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
