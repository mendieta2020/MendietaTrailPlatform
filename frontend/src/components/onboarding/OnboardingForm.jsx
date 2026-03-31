import React, { useState } from 'react';
import {
  TextField,
  MenuItem,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Alert,
} from '@mui/material';
import { ChevronDown, User, Activity, Heart, Target } from 'lucide-react';
import AvailabilityGrid from './AvailabilityGrid';
import { completeOnboarding } from '../../api/onboarding';

const BLOOD_TYPES = ['', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const CLOTHING_SIZES = ['', 'XS', 'S', 'M', 'L', 'XL', 'XXL'];
const GENDERS = [
  { value: '', label: 'Seleccionar' },
  { value: 'M', label: 'Masculino' },
  { value: 'F', label: 'Femenino' },
  { value: 'O', label: 'Otro' },
];
const TRAINING_TIMES = [
  { value: '', label: 'Sin preferencia' },
  { value: 'morning', label: 'Mañana' },
  { value: 'afternoon', label: 'Tarde' },
  { value: 'evening', label: 'Noche' },
];
const PRIORITIES = [
  { value: 'A', label: 'A — Carrera objetivo' },
  { value: 'B', label: 'B — Secundaria' },
  { value: 'C', label: 'C — Desarrollo' },
];

const DEFAULT_AVAILABILITY = Array.from({ length: 7 }, (_, i) => ({
  day_of_week: i,
  is_available: true,
  reason: '',
  preferred_time: '',
}));

export default function OnboardingForm({ invitationToken, joinSlug, invite, selectedPlanId, selectedPlanInfo }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Required fields
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [heightCm, setHeightCm] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [availability, setAvailability] = useState(DEFAULT_AVAILABILITY);

  // Optional personal
  const [gender, setGender] = useState('');
  const [province, setProvince] = useState('');
  const [city, setCity] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [instagramHandle, setInstagramHandle] = useState('');
  const [profession, setProfession] = useState('');
  const [bloodType, setBloodType] = useState('');
  const [clothingSize, setClothingSize] = useState('');
  const [emergencyName, setEmergencyName] = useState('');
  const [emergencyPhone, setEmergencyPhone] = useState('');

  // Optional athletic
  const [trainingAgeYears, setTrainingAgeYears] = useState('');
  const [pace1000m, setPace1000m] = useState('');
  const [maxHr, setMaxHr] = useState('');
  const [restingHr, setRestingHr] = useState('');
  const [vo2max, setVo2max] = useState('');
  const [weeklyHours, setWeeklyHours] = useState('');
  const [preferredTime, setPreferredTime] = useState('');
  const [best10k, setBest10k] = useState('');
  const [best21k, setBest21k] = useState('');
  const [best42k, setBest42k] = useState('');

  // Female health
  const [menstrualTracking, setMenstrualTracking] = useState(false);
  const [cycleDays, setCycleDays] = useState('');

  // Goal
  const [hasGoal, setHasGoal] = useState(false);
  const [raceName, setRaceName] = useState('');
  const [raceDate, setRaceDate] = useState('');
  const [distanceKm, setDistanceKm] = useState('');
  const [elevationM, setElevationM] = useState('');
  const [priority, setPriority] = useState('A');

  const intOrNull = (v) => (v === '' || v === null ? null : parseInt(v, 10));
  const floatOrNull = (v) => (v === '' || v === null ? null : parseFloat(v));

  const computeAge = () => {
    if (!birthDate) return null;
    const bd = new Date(birthDate);
    const today = new Date();
    let age = today.getFullYear() - bd.getFullYear();
    if (today.getMonth() < bd.getMonth() || (today.getMonth() === bd.getMonth() && today.getDate() < bd.getDate())) {
      age--;
    }
    return age;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const payload = {
      ...(invitationToken ? { invitation_token: invitationToken } : {}),
      ...(joinSlug ? { join_slug: joinSlug } : {}),
      first_name: firstName,
      last_name: lastName,
      birth_date: birthDate,
      weight_kg: parseFloat(weightKg),
      height_cm: parseFloat(heightCm),
      phone_number: phoneNumber,
      availability,
      // Optional
      gender,
      province,
      city,
      postal_code: postalCode,
      instagram_handle: instagramHandle,
      profession,
      blood_type: bloodType,
      clothing_size: clothingSize,
      emergency_contact_name: emergencyName,
      emergency_contact_phone: emergencyPhone,
      training_age_years: intOrNull(trainingAgeYears),
      pace_1000m_seconds: intOrNull(pace1000m),
      max_hr_bpm: intOrNull(maxHr),
      resting_hr_bpm: intOrNull(restingHr),
      vo2max: floatOrNull(vo2max),
      weekly_available_hours: intOrNull(weeklyHours),
      preferred_training_time: preferredTime,
      best_10k_minutes: intOrNull(best10k),
      best_21k_minutes: intOrNull(best21k),
      best_42k_minutes: intOrNull(best42k),
      menstrual_tracking_enabled: menstrualTracking,
      menstrual_cycle_days: intOrNull(cycleDays),
    };

    // Include selected plan if athlete chose it (no pre-assigned plan)
    if (selectedPlanId) {
      payload.coach_plan_id = selectedPlanId;
    }

    if (hasGoal && raceName && raceDate) {
      payload.goal = {
        race_name: raceName,
        race_date: raceDate,
        distance_km: floatOrNull(distanceKm),
        elevation_gain_m: floatOrNull(elevationM),
        priority,
      };
    }

    try {
      const { data } = await completeOnboarding(payload);
      if (data.redirect_url) {
        if (data.redirect_url.startsWith('http')) {
          window.location.href = data.redirect_url;
        } else {
          // Force full page reload so AuthContext + OrgContext pick up
          // the new Membership created during onboarding
          window.location.href = data.redirect_url;
        }
      } else {
        // Default: reload to dashboard with fresh session
        window.location.href = '/dashboard';
      }
    } catch (err) {
      const detail = err?.response?.data;
      if (typeof detail === 'object' && detail !== null) {
        const messages = Object.values(detail).flat();
        setError(messages.join(' '));
      } else {
        setError('Error al completar el registro. Intentá nuevamente.');
      }
    } finally {
      setLoading(false);
    }
  };

  const age = computeAge();

  return (
    <form onSubmit={handleSubmit} className="p-6 sm:p-8">
      <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-1">
        Paso 2 de 2
      </p>
      <h2 className="text-xl font-bold text-slate-900 mb-1">Completá tu perfil</h2>
      <p className="text-slate-500 text-sm mb-6">
        Tu coach necesita estos datos para personalizar tu entrenamiento
      </p>

      {error && (
        <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>
          {error}
        </Alert>
      )}

      {/* Required Section */}
      <div className="space-y-4 mb-6">
        <div className="grid grid-cols-2 gap-3">
          <TextField size="small" label="Nombre *" required value={firstName} onChange={(e) => setFirstName(e.target.value)} fullWidth />
          <TextField size="small" label="Apellido *" required value={lastName} onChange={(e) => setLastName(e.target.value)} fullWidth />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <TextField
            size="small"
            label="Fecha de nacimiento *"
            type="date"
            required
            value={birthDate}
            onChange={(e) => setBirthDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          <TextField
            size="small"
            label="Edad"
            value={age !== null ? `${age} años` : ''}
            disabled
            fullWidth
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <TextField size="small" label="Peso (kg) *" type="number" required value={weightKg} onChange={(e) => setWeightKg(e.target.value)} fullWidth />
          <TextField size="small" label="Altura (cm) *" type="number" required value={heightCm} onChange={(e) => setHeightCm(e.target.value)} fullWidth />
        </div>

        <TextField
          size="small"
          label="WhatsApp *"
          required
          placeholder="+54 9 11 1234-5678"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          fullWidth
        />

        <TextField size="small" select label="Género" value={gender} onChange={(e) => setGender(e.target.value)} fullWidth>
          {GENDERS.map((g) => <MenuItem key={g.value} value={g.value}>{g.label}</MenuItem>)}
        </TextField>

        {/* Availability */}
        <AvailabilityGrid value={availability} onChange={setAvailability} />
      </div>

      {/* Optional Sections */}
      <div className="space-y-2 mb-6">
        {/* Datos Deportivos */}
        <Accordion disableGutters elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: '12px !important', '&:before': { display: 'none' }, overflow: 'hidden' }}>
          <AccordionSummary expandIcon={<ChevronDown className="w-4 h-4" />}>
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" />
              <span className="text-sm font-medium text-slate-700">Datos deportivos (opcional)</span>
            </div>
          </AccordionSummary>
          <AccordionDetails>
            <div className="grid grid-cols-2 gap-3">
              <TextField size="small" label="Años de experiencia" type="number" value={trainingAgeYears} onChange={(e) => setTrainingAgeYears(e.target.value)} fullWidth />
              <TextField size="small" label="Horas semanales disponibles" type="number" value={weeklyHours} onChange={(e) => setWeeklyHours(e.target.value)} fullWidth />
              <TextField size="small" label="Ritmo 1000m (seg)" type="number" placeholder="Ej: 240" value={pace1000m} onChange={(e) => setPace1000m(e.target.value)} fullWidth />
              <TextField size="small" select label="Horario preferido" value={preferredTime} onChange={(e) => setPreferredTime(e.target.value)} fullWidth>
                {TRAINING_TIMES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
              </TextField>
              <TextField size="small" label="FC Máxima" type="number" value={maxHr} onChange={(e) => setMaxHr(e.target.value)} fullWidth />
              <TextField size="small" label="FC Reposo" type="number" value={restingHr} onChange={(e) => setRestingHr(e.target.value)} fullWidth />
              <TextField size="small" label="VO2max (ml/kg/min)" type="number" value={vo2max} onChange={(e) => setVo2max(e.target.value)} fullWidth />
              <div /> {/* spacer */}
              <TextField size="small" label="Mejor 10K (min)" type="number" placeholder="Ej: 45" value={best10k} onChange={(e) => setBest10k(e.target.value)} fullWidth />
              <TextField size="small" label="Mejor 21K (min)" type="number" placeholder="Ej: 100" value={best21k} onChange={(e) => setBest21k(e.target.value)} fullWidth />
              <TextField size="small" label="Mejor 42K (min)" type="number" placeholder="Ej: 220" value={best42k} onChange={(e) => setBest42k(e.target.value)} fullWidth />
            </div>
          </AccordionDetails>
        </Accordion>

        {/* Datos Personales */}
        <Accordion disableGutters elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: '12px !important', '&:before': { display: 'none' }, overflow: 'hidden' }}>
          <AccordionSummary expandIcon={<ChevronDown className="w-4 h-4" />}>
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-indigo-500" />
              <span className="text-sm font-medium text-slate-700">Datos personales (opcional)</span>
            </div>
          </AccordionSummary>
          <AccordionDetails>
            <div className="grid grid-cols-2 gap-3">
              <TextField size="small" label="Provincia" value={province} onChange={(e) => setProvince(e.target.value)} fullWidth />
              <TextField size="small" label="Localidad" value={city} onChange={(e) => setCity(e.target.value)} fullWidth />
              <TextField size="small" label="Código postal" value={postalCode} onChange={(e) => setPostalCode(e.target.value)} fullWidth />
              <TextField size="small" label="Instagram" placeholder="@usuario" value={instagramHandle} onChange={(e) => setInstagramHandle(e.target.value)} fullWidth />
              <TextField size="small" label="Profesión" value={profession} onChange={(e) => setProfession(e.target.value)} fullWidth />
              <TextField size="small" select label="Grupo sanguíneo" value={bloodType} onChange={(e) => setBloodType(e.target.value)} fullWidth>
                {BLOOD_TYPES.map((bt) => <MenuItem key={bt} value={bt}>{bt || 'Sin especificar'}</MenuItem>)}
              </TextField>
              <TextField size="small" select label="Talle remera" value={clothingSize} onChange={(e) => setClothingSize(e.target.value)} fullWidth>
                {CLOTHING_SIZES.map((cs) => <MenuItem key={cs} value={cs}>{cs || 'Sin especificar'}</MenuItem>)}
              </TextField>
              <div /> {/* spacer */}
              <TextField size="small" label="Contacto emergencia (nombre)" value={emergencyName} onChange={(e) => setEmergencyName(e.target.value)} fullWidth />
              <TextField size="small" label="Contacto emergencia (tel)" value={emergencyPhone} onChange={(e) => setEmergencyPhone(e.target.value)} fullWidth />
            </div>
          </AccordionDetails>
        </Accordion>

        {/* Salud Femenina */}
        {gender === 'F' && (
          <Accordion disableGutters elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: '12px !important', '&:before': { display: 'none' }, overflow: 'hidden' }}>
            <AccordionSummary expandIcon={<ChevronDown className="w-4 h-4" />}>
              <div className="flex items-center gap-2">
                <Heart className="w-4 h-4 text-pink-500" />
                <span className="text-sm font-medium text-slate-700">Salud femenina (opcional)</span>
              </div>
            </AccordionSummary>
            <AccordionDetails>
              <div className="space-y-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={menstrualTracking}
                    onChange={(e) => setMenstrualTracking(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-slate-700">Quiero registrar mi ciclo menstrual</span>
                </label>
                {menstrualTracking && (
                  <TextField
                    size="small"
                    label="Duración promedio del ciclo (días)"
                    type="number"
                    placeholder="Ej: 28"
                    value={cycleDays}
                    onChange={(e) => setCycleDays(e.target.value)}
                    sx={{ maxWidth: 260 }}
                  />
                )}
              </div>
            </AccordionDetails>
          </Accordion>
        )}

        {/* Objetivo de carrera */}
        <Accordion disableGutters elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: '12px !important', '&:before': { display: 'none' }, overflow: 'hidden' }}>
          <AccordionSummary expandIcon={<ChevronDown className="w-4 h-4" />}>
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-indigo-500" />
              <span className="text-sm font-medium text-slate-700">Objetivo de carrera (opcional)</span>
            </div>
          </AccordionSummary>
          <AccordionDetails>
            <div className="space-y-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={hasGoal}
                  onChange={(e) => setHasGoal(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-slate-700">Tengo una carrera objetivo</span>
              </label>
              {hasGoal && (
                <div className="grid grid-cols-2 gap-3">
                  <TextField size="small" label="Nombre de la carrera" required={hasGoal} value={raceName} onChange={(e) => setRaceName(e.target.value)} fullWidth />
                  <TextField size="small" label="Fecha" type="date" required={hasGoal} value={raceDate} onChange={(e) => setRaceDate(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
                  <TextField size="small" label="Distancia (km)" type="number" value={distanceKm} onChange={(e) => setDistanceKm(e.target.value)} fullWidth />
                  <TextField size="small" label="Desnivel+ (m)" type="number" value={elevationM} onChange={(e) => setElevationM(e.target.value)} fullWidth />
                  <TextField size="small" select label="Prioridad" value={priority} onChange={(e) => setPriority(e.target.value)} fullWidth>
                    {PRIORITIES.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
                  </TextField>
                </div>
              )}
            </div>
          </AccordionDetails>
        </Accordion>
      </div>

      {/* Plan info reminder */}
      {(invite?.plan_name || selectedPlanInfo) && (
        <div className="bg-indigo-50 rounded-xl p-4 mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-indigo-500 font-semibold uppercase">Tu plan</p>
            <p className="text-sm font-bold text-indigo-900">
              {invite?.plan_name || selectedPlanInfo?.name}
            </p>
          </div>
          <p className="text-lg font-bold text-indigo-600">
            {new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(invite?.price || selectedPlanInfo?.price || 0)}
            <span className="text-xs font-normal text-indigo-400">/mes</span>
          </p>
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
      >
        {loading ? (
          <CircularProgress size={18} sx={{ color: 'white' }} />
        ) : (
          'Completar registro y continuar al pago'
        )}
      </button>
    </form>
  );
}
