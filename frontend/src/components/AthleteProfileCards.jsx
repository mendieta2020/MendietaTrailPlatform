import React from 'react';
import {
  Box, Typography, Paper, Button, TextField, MenuItem, Chip, Switch, FormControlLabel,
} from '@mui/material';
import {
  User, Activity, Calendar, Target, Heart, MapPin, Phone, Instagram,
  Briefcase, Droplet, Shirt, AlertTriangle, Plus, Trash2, Check, X,
} from 'lucide-react';
import { Edit2, Save } from 'lucide-react';

const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

const TRAINING_TIME_LABELS = {
  morning: 'Mañana',
  afternoon: 'Tarde',
  evening: 'Noche',
};

const TRAINING_TIME_OPTIONS = [
  { value: 'morning', label: 'Mañana' },
  { value: 'afternoon', label: 'Tarde' },
  { value: 'evening', label: 'Noche' },
];

const BLOOD_TYPE_OPTIONS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const CLOTHING_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];

const SEVERITY_COLORS = {
  leve: { bg: '#FEF3C7', text: '#92400E' },
  moderada: { bg: '#FED7AA', text: '#9A3412' },
  severa: { bg: '#FEE2E2', text: '#991B1B' },
};

const STATUS_LABELS = {
  activa: '🔴 Activa',
  en_recuperacion: '🟡 En recuperación',
  resuelta: '🟢 Resuelta',
};

function getMenstrualPhase(lastPeriodDate, cycleDays) {
  if (!lastPeriodDate || !cycleDays) return null;
  const today = new Date();
  const lastPeriod = new Date(lastPeriodDate);
  const daysSince = Math.floor((today - lastPeriod) / 86400000);
  const dayInCycle = ((daysSince % cycleDays) + cycleDays) % cycleDays;
  if (dayInCycle <= 5) return { name: 'Menstrual', emoji: '🔴', color: '#EF4444', tip: 'Hormonas en nivel bajo. Escuchá a tu cuerpo.' };
  if (dayInCycle <= 13) return { name: 'Folicular', emoji: '🟢', color: '#10B981', tip: 'Momento ideal para alta intensidad y fuerza.' };
  if (dayInCycle <= 15) return { name: 'Ovulación', emoji: '🟡', color: '#F59E0B', tip: 'Pico de energía. Aprovechá para sesiones exigentes.' };
  return { name: 'Lútea', emoji: '🟠', color: '#F97316', tip: 'Reducí intensidad. Priorizá trabajo aeróbico y recuperación.' };
}

function CardHeader({ icon, title, cardName, editingCard, readOnly, onEditCard, onSaveCard, onCancelEdit }) {
  const isEditing = editingCard === cardName;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {icon}
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{title}</Typography>
      </Box>
      {!readOnly && !isEditing && (
        <Button size="small" startIcon={<Edit2 size={12} />} onClick={() => onEditCard(cardName)}
          sx={{ textTransform: 'none', color: '#6366F1', fontSize: '0.8rem' }}>
          Editar
        </Button>
      )}
      {!readOnly && isEditing && (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="contained" onClick={() => onSaveCard(cardName)}
            startIcon={<Save size={12} />}
            sx={{ textTransform: 'none', bgcolor: '#6366F1', fontSize: '0.8rem', '&:hover': { bgcolor: '#4F46E5' } }}>
            Guardar
          </Button>
          <Button size="small" onClick={onCancelEdit}
            sx={{ textTransform: 'none', color: '#64748B', fontSize: '0.8rem' }}>
            Cancelar
          </Button>
        </Box>
      )}
    </Box>
  );
}

/**
 * Shared profile cards component.
 * Used by AthleteProfile (editable) and AthleteDetail coach view (readOnly).
 */
export function AthleteProfileCards({
  profile,
  injuries = [],
  availability = [],
  goals = [],
  userName = '',
  readOnly = false,
  editingCard = null,
  editDraft = {},
  onEditCard,
  onSaveCard,
  onCancelEdit,
  onDraftChange,
  onAddInjury,
  onDeleteInjury,
}) {
  const phase = profile?.menstrual_tracking_enabled
    ? getMenstrualPhase(profile.last_period_date, profile.menstrual_cycle_days)
    : null;

  const isEditing = (cardName) => !readOnly && editingCard === cardName;
  const d = editDraft || {};

  return (
    <>
      {/* Card 1: Datos Personales */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
        <CardHeader
          icon={<User className="w-5 h-5" style={{ color: '#6366F1' }} />}
          title="Datos Personales"
          cardName="personal"
          editingCard={editingCard}
          readOnly={readOnly}
          onEditCard={onEditCard}
          onSaveCard={onSaveCard}
          onCancelEdit={onCancelEdit}
        />
        {isEditing('personal') ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <TextField size="small" label="Instagram" value={d.instagram_handle ?? ''}
              onChange={(e) => onDraftChange('instagram_handle', e.target.value)} />
            <TextField size="small" label="Profesión" value={d.profession ?? ''}
              onChange={(e) => onDraftChange('profession', e.target.value)} />
            <TextField select size="small" label="Grupo sanguíneo" value={d.blood_type ?? ''}
              onChange={(e) => onDraftChange('blood_type', e.target.value)}>
              <MenuItem value=""><em>—</em></MenuItem>
              {BLOOD_TYPE_OPTIONS.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
            </TextField>
            <TextField select size="small" label="Talle" value={d.clothing_size ?? ''}
              onChange={(e) => onDraftChange('clothing_size', e.target.value)}>
              <MenuItem value=""><em>—</em></MenuItem>
              {CLOTHING_SIZE_OPTIONS.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
            </TextField>
            <TextField size="small" label="Contacto de emergencia" value={d.emergency_contact_name ?? ''}
              onChange={(e) => onDraftChange('emergency_contact_name', e.target.value)} />
            <TextField size="small" label="Tel. emergencia" value={d.emergency_contact_phone ?? ''}
              onChange={(e) => onDraftChange('emergency_contact_phone', e.target.value)} />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <div><span className="text-slate-500">Nombre:</span> <strong>{userName}</strong></div>
              <div><span className="text-slate-500">Edad:</span> <strong>{profile?.age || '—'} años</strong></div>
              <div><span className="text-slate-500">Nacimiento:</span> <strong>{profile?.birth_date || '—'}</strong></div>
              <div className="flex items-center gap-1"><Phone className="w-3 h-3 text-slate-400" /> <strong>{profile?.phone_number || '—'}</strong></div>
              <div className="flex items-center gap-1"><Instagram className="w-3 h-3 text-slate-400" /> <strong>{profile?.instagram_handle || '—'}</strong></div>
              <div className="flex items-center gap-1"><Briefcase className="w-3 h-3 text-slate-400" /> <strong>{profile?.profession || '—'}</strong></div>
              <div className="flex items-center gap-1"><Droplet className="w-3 h-3 text-slate-400" /> <strong>{profile?.blood_type || '—'}</strong></div>
              <div className="flex items-center gap-1"><Shirt className="w-3 h-3 text-slate-400" /> Talle: <strong>{profile?.clothing_size || '—'}</strong></div>
              <div className="flex items-center gap-1"><MapPin className="w-3 h-3 text-slate-400" /> <strong>{profile?.location_city || '—'}</strong></div>
            </div>
            {profile?.emergency_contact_name && (
              <div className="mt-2 text-sm text-slate-500">
                🆘 Emergencia: <strong>{profile.emergency_contact_name}</strong> — {profile.emergency_contact_phone}
              </div>
            )}
          </>
        )}
      </Paper>

      {/* Card 2: Datos Físicos & Deportivos */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
        <CardHeader
          icon={<Activity className="w-5 h-5" style={{ color: '#10B981' }} />}
          title="Datos Físicos & Deportivos"
          cardName="physical"
          editingCard={editingCard}
          readOnly={readOnly}
          onEditCard={onEditCard}
          onSaveCard={onSaveCard}
          onCancelEdit={onCancelEdit}
        />
        {isEditing('physical') ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <TextField size="small" label="Peso (kg)" type="number" value={d.weight_kg ?? ''}
              onChange={(e) => onDraftChange('weight_kg', e.target.value)} />
            <TextField size="small" label="Altura (cm)" type="number" value={d.height_cm ?? ''}
              onChange={(e) => onDraftChange('height_cm', e.target.value)} />
            <TextField size="small" label="FC Máx (bpm)" type="number" value={d.max_hr_bpm ?? ''}
              onChange={(e) => onDraftChange('max_hr_bpm', e.target.value)} />
            <TextField size="small" label="FC Reposo (bpm)" type="number" value={d.resting_hr_bpm ?? ''}
              onChange={(e) => onDraftChange('resting_hr_bpm', e.target.value)} />
            <TextField size="small" label="VO2max" type="number" value={d.vo2max ?? ''}
              onChange={(e) => onDraftChange('vo2max', e.target.value)} />
            <TextField size="small" label="Exp. entreno (años)" type="number" value={d.training_age_years ?? ''}
              onChange={(e) => onDraftChange('training_age_years', e.target.value)} />
            <TextField size="small" label="Horas/semana" type="number" value={d.weekly_available_hours ?? ''}
              onChange={(e) => onDraftChange('weekly_available_hours', e.target.value)} />
            <TextField select size="small" label="Horario preferido" value={d.preferred_training_time ?? ''}
              onChange={(e) => onDraftChange('preferred_training_time', e.target.value)}>
              <MenuItem value=""><em>—</em></MenuItem>
              {TRAINING_TIME_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </TextField>
            <TextField size="small" label="Ritmo 1000m (seg)" type="number" value={d.pace_1000m_seconds ?? ''}
              onChange={(e) => onDraftChange('pace_1000m_seconds', e.target.value)} />
            <TextField size="small" label="Mejor 10K (min)" type="number" value={d.best_10k_minutes ?? ''}
              onChange={(e) => onDraftChange('best_10k_minutes', e.target.value)} />
            <TextField size="small" label="Mejor 21K (min)" type="number" value={d.best_21k_minutes ?? ''}
              onChange={(e) => onDraftChange('best_21k_minutes', e.target.value)} />
            <TextField size="small" label="Mejor 42K (min)" type="number" value={d.best_42k_minutes ?? ''}
              onChange={(e) => onDraftChange('best_42k_minutes', e.target.value)} />
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div><span className="text-slate-500">Peso:</span> <strong>{profile?.weight_kg || '—'} kg</strong></div>
            <div><span className="text-slate-500">Altura:</span> <strong>{profile?.height_cm || '—'} cm</strong></div>
            <div><span className="text-slate-500">FC Max:</span> <strong>{profile?.max_hr_bpm || '—'} bpm</strong></div>
            <div><span className="text-slate-500">FC Reposo:</span> <strong>{profile?.resting_hr_bpm || '—'} bpm</strong></div>
            <div><span className="text-slate-500">VO2max:</span> <strong>{profile?.vo2max || '—'}</strong></div>
            <div><span className="text-slate-500">Experiencia:</span> <strong>{profile?.training_age_years || '—'} años</strong></div>
            <div><span className="text-slate-500">Horas/semana:</span> <strong>{profile?.weekly_available_hours || '—'}h</strong></div>
            <div>
              <span className="text-slate-500">Horario:</span>{' '}
              <strong>{TRAINING_TIME_LABELS[profile?.preferred_training_time] || profile?.preferred_training_time || '—'}</strong>
            </div>
            <div><span className="text-slate-500">Ritmo 1000m:</span> <strong>{profile?.pace_1000m_seconds || '—'}s</strong></div>
            {profile?.best_10k_minutes > 0 && <div><span className="text-slate-500">10K:</span> <strong>{profile.best_10k_minutes} min</strong></div>}
            {profile?.best_21k_minutes > 0 && <div><span className="text-slate-500">21K:</span> <strong>{profile.best_21k_minutes} min</strong></div>}
            {profile?.best_42k_minutes > 0 && <div><span className="text-slate-500">42K:</span> <strong>{profile.best_42k_minutes} min</strong></div>}
          </div>
        )}
      </Paper>

      {/* Card 3: Disponibilidad Semanal */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Calendar className="w-5 h-5" style={{ color: '#F59E0B' }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Disponibilidad Semanal</Typography>
        </Box>
        <div className="flex gap-2 flex-wrap">
          {availability.length > 0 ? availability.map((a) => (
            <div key={a.day_of_week}
              className={`flex flex-col items-center p-2 rounded-lg border ${a.is_available ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
              <span className="text-xs font-bold">{DAYS[a.day_of_week]}</span>
              {a.is_available ? <Check className="w-4 h-4 text-emerald-600" /> : <X className="w-4 h-4 text-red-500" />}
              {!a.is_available && a.reason && <span className="text-xs text-red-600 mt-0.5">{a.reason}</span>}
            </div>
          )) : <span className="text-sm text-slate-400">Sin datos de disponibilidad</span>}
        </div>
      </Paper>

      {/* Card 4: Objetivos de Carrera */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Target className="w-5 h-5" style={{ color: '#8B5CF6' }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Objetivos de Carrera</Typography>
        </Box>
        {goals.length > 0 ? (
          <div className="space-y-2">
            {goals.map((g) => (
              <div key={g.id} className="flex items-center justify-between bg-slate-50 rounded-lg p-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Chip label={`Prioridad ${g.priority}`} size="small"
                      sx={{
                        bgcolor: g.priority === 'A' ? '#DBEAFE' : g.priority === 'B' ? '#FEF3C7' : '#F3F4F6',
                        color: g.priority === 'A' ? '#1E40AF' : g.priority === 'B' ? '#92400E' : '#374151',
                        fontWeight: 700, fontSize: '0.7rem',
                      }} />
                    <strong className="text-sm">{g.title}</strong>
                  </div>
                  <span className="text-xs text-slate-500">
                    {g.target_date}
                    {g.target_event?.distance_km ? ` — ${g.target_event.distance_km}km` : ''}
                    {g.target_event?.elevation_gain_m ? ` — D+${g.target_event.elevation_gain_m}m` : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <span className="text-sm text-slate-400">Sin objetivos de carrera configurados</span>
        )}
      </Paper>

      {/* Card 5: Lesiones */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AlertTriangle className="w-5 h-5" style={{ color: '#EF4444' }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Lesiones</Typography>
          </Box>
          {!readOnly && (
            <Button size="small" startIcon={<Plus className="w-4 h-4" />} onClick={onAddInjury}
              sx={{ textTransform: 'none', color: '#6366F1' }}>
              Agregar lesión
            </Button>
          )}
        </Box>
        {injuries.length > 0 ? (
          <div className="space-y-2">
            {injuries.map((inj) => (
              <div key={inj.id} className="bg-slate-50 rounded-lg p-3 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Chip label={inj.body_zone?.replace('_', ' ')} size="small"
                      sx={{ bgcolor: SEVERITY_COLORS[inj.severity]?.bg, color: SEVERITY_COLORS[inj.severity]?.text, fontWeight: 600, fontSize: '0.7rem' }} />
                    <span className="text-xs text-slate-500">{STATUS_LABELS[inj.status] || inj.status}</span>
                  </div>
                  <span className="text-sm">{inj.injury_type} — {inj.side}</span>
                  {inj.description && <p className="text-xs text-slate-500 mt-0.5">{inj.description}</p>}
                  <span className="text-xs text-slate-400">Desde: {inj.date_occurred}</span>
                </div>
                {!readOnly && (
                  <button onClick={() => onDeleteInjury(inj.id)} className="text-slate-400 hover:text-red-500 p-1">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <span className="text-sm text-slate-400">Sin lesiones reportadas</span>
        )}
      </Paper>

      {/* Card 6: Salud Femenina — show always for athlete, only when enabled for coach */}
      {(!readOnly || profile?.menstrual_tracking_enabled) && (
        <Paper sx={{ p: 3, borderRadius: 3, mb: 3 }}>
          <CardHeader
            icon={<Heart className="w-5 h-5" style={{ color: '#EC4899' }} />}
            title="Salud Femenina"
            cardName="health"
            editingCard={editingCard}
            readOnly={readOnly}
            onEditCard={onEditCard}
            onSaveCard={onSaveCard}
            onCancelEdit={onCancelEdit}
          />
          {isEditing('health') ? (
            <div className="grid grid-cols-2 gap-3">
              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(d.menstrual_tracking_enabled)}
                    onChange={(e) => onDraftChange('menstrual_tracking_enabled', e.target.checked)}
                  />
                }
                label="Activar tracking"
              />
              <TextField size="small" label="Duración ciclo (días)" type="number"
                value={d.menstrual_cycle_days ?? ''}
                onChange={(e) => onDraftChange('menstrual_cycle_days', e.target.value)} />
              <TextField size="small" type="date" label="Fecha último periodo"
                value={d.last_period_date ?? ''}
                onChange={(e) => onDraftChange('last_period_date', e.target.value)}
                slotProps={{ inputLabel: { shrink: true } }} />
            </div>
          ) : profile?.menstrual_tracking_enabled ? (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                <div><span className="text-slate-500">Duración ciclo:</span> <strong>{profile.menstrual_cycle_days || '—'} días</strong></div>
                <div><span className="text-slate-500">Último periodo:</span> <strong>{profile.last_period_date || '—'}</strong></div>
              </div>
              {phase && (
                <div className="rounded-xl p-3" style={{ backgroundColor: phase.color + '15', border: `1px solid ${phase.color}30` }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{phase.emoji}</span>
                    <strong className="text-sm" style={{ color: phase.color }}>Fase actual: {phase.name}</strong>
                  </div>
                  <p className="text-xs text-slate-600">{phase.tip}</p>
                </div>
              )}
            </>
          ) : (
            <span className="text-sm text-slate-400">Tracking menstrual no activado</span>
          )}
        </Paper>
      )}
    </>
  );
}
