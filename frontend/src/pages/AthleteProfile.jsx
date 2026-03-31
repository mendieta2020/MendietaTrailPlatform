import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Button, CircularProgress, Alert,
} from '@mui/material';
import { MapPin } from 'lucide-react';
import AthleteLayout from '../components/AthleteLayout';
import { AthleteProfileCards } from '../components/AthleteProfileCards';
import { useAuth } from '../context/AuthContext';
import {
  getAthleteProfile, updateAthleteProfile, getInjuries, createInjury,
  deleteInjury, getAvailability, getGoals,
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

  // Inline editing state
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
          }).finally(() => setLoading(false));
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  }, [orgId]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2000);
  };

  const handleEditCard = (cardName) => {
    setEditDraft({ ...profile });
    setEditingCard(cardName);
  };

  const handleCancelEdit = () => {
    setEditingCard(null);
    setEditDraft({});
  };

  const handleSaveCard = async (cardName) => {
    if (!orgId || !athleteId) return;
    const fields = CARD_FIELDS[cardName] || [];
    const patch = {};
    fields.forEach(f => {
      if (editDraft[f] !== undefined) patch[f] = editDraft[f] === '' ? null : editDraft[f];
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

  const handleAddInjury = async () => {
    if (!orgId || !athleteId) return;
    try {
      const { data } = await createInjury(orgId, athleteId, {
        injury_type: 'muscular',
        body_zone: 'rodilla',
        side: 'derecho',
        severity: 'leve',
        description: '',
        date_occurred: new Date().toISOString().split('T')[0],
        status: 'activa',
      });
      setInjuries(prev => [data, ...prev]);
    } catch {
      showToast('Error al agregar lesión');
    }
  };

  const handleDeleteInjury = async (id) => {
    if (!orgId || !athleteId) return;
    try {
      await deleteInjury(orgId, athleteId, id);
      setInjuries(prev => prev.filter(i => i.id !== id));
    } catch {
      showToast('Error al eliminar');
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
          <Alert severity={toast === 'Guardado' ? 'success' : 'error'} sx={{ mb: 2, borderRadius: 2 }}>
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
          onAddInjury={handleAddInjury}
          onDeleteInjury={handleDeleteInjury}
        />

        {/* Device + Location */}
        <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <MapPin className="w-5 h-5" style={{ color: '#F97316' }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Conexiones & Ubicación</Typography>
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
