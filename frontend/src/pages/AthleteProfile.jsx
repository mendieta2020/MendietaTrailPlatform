import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Button, CircularProgress, Alert, TextField,
} from '@mui/material';
import { MapPin } from 'lucide-react';
import AthleteLayout from '../components/AthleteLayout';
import { AthleteProfileCards } from '../components/AthleteProfileCards';
import { useAuth } from '../context/AuthContext';
import {
  getAthleteProfile, updateAthleteProfile, getInjuries, createInjury,
  updateInjury, deleteInjury, getAvailability, updateAvailability,
  getGoals, createGoal, updateGoal, deleteGoal, updateAthleteRecord,
} from '../api/athlete';
import client from '../api/client';

const PERSONAL_FIELDS = [
  'instagram_handle', 'profession', 'blood_type', 'clothing_size',
  'emergency_contact_name', 'emergency_contact_phone',
];

const PHYSICAL_FIELDS = [
  'weight_kg', 'height_cm', 'max_hr_bpm', 'resting_hr_bpm', 'vo2max',
  'training_age_years', 'weekly_available_hours', 'preferred_training_time',
  'pace_1000m_seconds', 'best_10k_minutes', 'best_21k_minutes', 'best_42k_minutes',
];

const HEALTH_FIELDS = ['menstrual_tracking_enabled', 'menstrual_cycle_days', 'last_period_date'];

const CARD_FIELDS = { personal: PERSONAL_FIELDS, physical: PHYSICAL_FIELDS, health: HEALTH_FIELDS };

const AthleteProfile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const orgId = user?.memberships?.[0]?.org_id;

  const [profile, setProfile] = useState(null);
  const [injuries, setInjuries] = useState([]);
  const [availability, setAvailability] = useState([]);
  const [goals, setGoals] = useState([]);
  const [athleteId, setAthleteId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState('');
  // PR-161: location city (on Athlete model, not AthleteProfile)
  const [locationCity, setLocationCity] = useState('');
  const [locationDraft, setLocationDraft] = useState('');
  const [editingLocation, setEditingLocation] = useState(false);
  const [savingLocation, setSavingLocation] = useState(false);

  // Inline editing state for Cards 1, 2, 6 (profile PATCH)
  const [editingCard, setEditingCard] = useState(null);
  const [editDraft, setEditDraft] = useState({});

  useEffect(() => {
    if (!orgId) return;
    client.get(`/api/p1/orgs/${orgId}/roster/athletes/`)
      .then(res => {
        const data = res.data?.results ?? res.data ?? [];
        const athletes = Array.isArray(data) ? data : [];
        if (athletes.length > 0) {
          const ath = athletes[0];
          setAthleteId(ath.id);
          Promise.all([
            getAthleteProfile(orgId, ath.id).catch(() => ({ data: null })),
            getInjuries(orgId, ath.id).catch(() => ({ data: [] })),
            getAvailability(orgId, ath.id).catch(() => ({ data: [] })),
            getGoals(orgId).catch(() => ({ data: [] })),
          ]).then(([profRes, injRes, availRes, goalRes]) => {
            if (profRes.data) setProfile(profRes.data);
            setInjuries(Array.isArray(injRes.data) ? injRes.data : injRes.data?.results ?? []);
            setAvailability(Array.isArray(availRes.data) ? availRes.data : availRes.data?.results ?? []);
            const allGoals = Array.isArray(goalRes.data) ? goalRes.data : goalRes.data?.results ?? [];
            setGoals(allGoals.filter(g => g.status === 'active'));
            // Load location_city from the Athlete record itself
            const city = ath.location_city ?? '';
            setLocationCity(city);
            setLocationDraft(city);
          }).finally(() => setLoading(false));
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  }, [orgId]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  };

  // ── Cards 1, 2, 6: profile PATCH ────────────────────────────────────────────

  const handleEditCard = (cardName) => {
    setEditDraft({ ...profile });
    setEditingCard(cardName);
  };

  const handleCancelEdit = () => {
    setEditingCard(null);
    setEditDraft({});
  };

  const PROFILE_CHAR_FIELDS = new Set([
    'instagram_handle', 'profession', 'blood_type', 'clothing_size',
    'emergency_contact_name', 'emergency_contact_phone', 'preferred_training_time',
  ]);
  const handleSaveCard = async (cardName) => {
    if (!orgId || !athleteId) return;
    const fields = CARD_FIELDS[cardName] || [];
    const patch = {};
    fields.forEach(f => {
      if (editDraft[f] !== undefined) {
        // CharField (blank=True) fields: send "" not null
        patch[f] = (editDraft[f] === '' && !PROFILE_CHAR_FIELDS.has(f)) ? null : (editDraft[f] ?? '');
      }
    });
    try {
      await updateAthleteProfile(orgId, athleteId, patch);
      setProfile(prev => ({ ...prev, ...patch }));
      setEditingCard(null);
      setEditDraft({});
      showToast('Guardado');
    } catch {
      showToast('Error al guardar');
    }
  };

  const handleDraftChange = (field, value) => {
    setEditDraft(prev => ({ ...prev, [field]: value }));
  };

  // ── Card 3: Availability bulk PUT ────────────────────────────────────────────

  const handleSaveAvailability = async (availData) => {
    if (!orgId || !athleteId) return;
    try {
      const { data } = await updateAvailability(orgId, athleteId, availData);
      setAvailability(Array.isArray(data) ? data : data?.results ?? []);
      showToast('Disponibilidad guardada');
    } catch {
      showToast('Error al guardar disponibilidad');
      throw new Error('availability_save_failed');
    }
  };

  // ── Card 4: Goals create / delete ────────────────────────────────────────────

  const handleAddGoal = async (goalData) => {
    if (!orgId) return;
    if (!athleteId) {
      showToast('Error: perfil no cargado. Recargá la página.');
      throw new Error('athlete_id_missing');
    }
    try {
      const { data } = await createGoal(orgId, { ...goalData, athlete_id: athleteId });
      setGoals(prev => [...prev, data]);
      showToast('Objetivo agregado');
    } catch (err) {
      if (err.message === 'athlete_id_missing') throw err;
      showToast('Error al agregar objetivo');
      throw new Error('goal_add_failed');
    }
  };

  const handleUpdateGoal = async (goalId, data) => {
    if (!orgId) return;
    try {
      const { data: updated } = await updateGoal(orgId, goalId, data);
      setGoals(prev => prev.map(g => g.id === goalId ? { ...g, ...updated } : g));
      showToast('Objetivo actualizado');
    } catch {
      showToast('Error al actualizar objetivo');
      throw new Error('goal_update_failed');
    }
  };

  const handleDeleteGoal = async (goalId) => {
    if (!orgId) return;
    try {
      await deleteGoal(orgId, goalId);
      setGoals(prev => prev.filter(g => g.id !== goalId));
      showToast('Objetivo eliminado');
    } catch {
      showToast('Error al eliminar objetivo');
    }
  };

  // ── Card 5: Injuries CRUD ────────────────────────────────────────────────────

  const handleSaveInjury = async (data, injuryId) => {
    if (!orgId || !athleteId) return;
    try {
      if (injuryId) {
        const { data: updated } = await updateInjury(orgId, athleteId, injuryId, data);
        setInjuries(prev => prev.map(i => i.id === injuryId ? updated : i));
        showToast('Lesión actualizada');
      } else {
        const { data: created } = await createInjury(orgId, athleteId, data);
        setInjuries(prev => [created, ...prev]);
        showToast('Lesión registrada');
      }
    } catch {
      showToast('Error al guardar lesión');
      throw new Error('injury_save_failed');
    }
  };

  const handleDeleteInjury = async (id) => {
    if (!orgId || !athleteId) return;
    try {
      await deleteInjury(orgId, athleteId, id);
      setInjuries(prev => prev.filter(i => i.id !== id));
      showToast('Lesión eliminada');
    } catch {
      showToast('Error al eliminar');
    }
  };

  const handleSaveLocation = async () => {
    if (!orgId || !athleteId) return;
    setSavingLocation(true);
    try {
      await updateAthleteRecord(orgId, athleteId, { location_city: locationDraft });
      setLocationCity(locationDraft);
      setEditingLocation(false);
      showToast('Ubicación guardada');
    } catch {
      showToast('Error al guardar ubicación');
    } finally {
      setSavingLocation(false);
    }
  };

  if (loading) {
    return (
      <AthleteLayout user={user}>
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      </AthleteLayout>
    );
  }

  const userName = `${user?.first_name || ''} ${user?.last_name || ''}`.trim();

  return (
    <AthleteLayout user={user}>
      <Box sx={{ maxWidth: 800, mx: 'auto' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A', mb: 3 }}>
          Mi Perfil
        </Typography>

        {toast && (
          <Alert severity={toast.startsWith('Error') ? 'error' : 'success'} sx={{ mb: 2, borderRadius: 2 }}>
            {toast}
          </Alert>
        )}

        <AthleteProfileCards
          profile={profile}
          injuries={injuries}
          availability={availability}
          goals={goals}
          userName={userName}
          readOnly={false}
          editingCard={editingCard}
          editDraft={editDraft}
          onEditCard={handleEditCard}
          onSaveCard={handleSaveCard}
          onCancelEdit={handleCancelEdit}
          onDraftChange={handleDraftChange}
          onSaveAvailability={handleSaveAvailability}
          onAddGoal={handleAddGoal}
          onUpdateGoal={handleUpdateGoal}
          onDeleteGoal={handleDeleteGoal}
          onSaveInjury={handleSaveInjury}
          onDeleteInjury={handleDeleteInjury}
          orgId={orgId}
          athleteId={athleteId}
        />

        {/* Device + Location — PR-161 */}
        <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <MapPin className="w-5 h-5" style={{ color: '#F97316' }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Conexiones & Ubicación</Typography>
          </Box>

          {/* Location city */}
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', mb: 0.5 }}>
              Ciudad
            </Typography>
            {editingLocation ? (
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <TextField
                  size="small"
                  placeholder="Ej: Buenos Aires, Argentina"
                  value={locationDraft}
                  onChange={e => setLocationDraft(e.target.value)}
                  sx={{ flex: 1 }}
                />
                <Button
                  size="small"
                  variant="contained"
                  onClick={handleSaveLocation}
                  disabled={savingLocation}
                  sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65100' }, textTransform: 'none', minWidth: 80 }}
                >
                  {savingLocation ? <CircularProgress size={12} sx={{ color: '#fff' }} /> : 'Guardar'}
                </Button>
                <Button size="small" onClick={() => { setEditingLocation(false); setLocationDraft(locationCity); }} sx={{ textTransform: 'none', color: '#64748b' }}>
                  Cancelar
                </Button>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2" sx={{ color: '#1e293b', fontWeight: 500 }}>
                  {locationCity || '—'}
                </Typography>
                <Button size="small" onClick={() => setEditingLocation(true)} sx={{ color: '#F57C00', fontSize: '0.75rem', minWidth: 'auto', p: 0.5 }}>
                  Editar
                </Button>
              </Box>
            )}
            <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.68rem', display: 'block', mt: 0.5 }}>
              Tu ubicación se usa para mostrar el clima en tus sesiones
            </Typography>
          </Box>

          <Button variant="outlined" size="small" onClick={() => navigate('/connections')} sx={{ textTransform: 'none' }}>
            Gestionar conexiones de dispositivo
          </Button>
        </Paper>
      </Box>
    </AthleteLayout>
  );
};

export default AthleteProfile;
