import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Divider,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  MenuItem,
  Link,
} from '@mui/material';
import Joyride from 'react-joyride';
import client from '../../api/client';
import { Link as RouterLink } from 'react-router-dom';

const stepLabels = [
  'Conectar Strava',
  'Crear primer atleta',
  'Asignar plantilla',
  'Tour PMC & Alertas',
];

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function OnboardingWizard({ open, onClose, onComplete }) {
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [creatingAthlete, setCreatingAthlete] = useState(false);
  const [assigningTemplate, setAssigningTemplate] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [athleteForm, setAthleteForm] = useState({ nombre: '', apellido: '', email: '' });
  const [createdAthlete, setCreatedAthlete] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [templateDate, setTemplateDate] = useState(todayISO());
  const [runTour, setRunTour] = useState(false);

  useEffect(() => {
    if (!open) {
      setActiveStep(0);
      setError('');
      setSuccess('');
      setRunTour(false);
    }
  }, [open]);

  useEffect(() => {
    let cancelled = false;

    async function fetchTemplates() {
      try {
        const res = await client.get('/api/plantillas/');
        if (cancelled) return;
        const payload = res.data?.results ?? res.data ?? [];
        setTemplates(Array.isArray(payload) ? payload : []);
      } catch {
        if (!cancelled) setTemplates([]);
      }
    }

    if (open) {
      fetchTemplates();
    }

    return () => {
      cancelled = true;
    };
  }, [open]);

  const templateOptions = useMemo(() => {
    return templates.map((t) => ({
      id: t.id,
      titulo: t.titulo,
      deporte: t.deporte,
      dificultad: t.dificultad_display || t.etiqueta_dificultad,
      descripcion: t.descripcion_global,
    }));
  }, [templates]);

  const joyrideSteps = [
    {
      target: '#pmc-widget',
      content: 'Aquí ves el PMC: Fitness (CTL) y Fatiga (ATL) para seguir tendencias.',
      disableBeacon: true,
    },
    {
      target: '#alerts-widget',
      content: 'Estas alertas resaltan cambios relevantes para priorizar revisiones rápidas.',
    },
  ];

  const handleNext = () => {
    setError('');
    setSuccess('');
    setActiveStep((prev) => Math.min(prev + 1, stepLabels.length - 1));
  };

  const handleBack = () => {
    setError('');
    setSuccess('');
    setActiveStep((prev) => Math.max(prev - 1, 0));
  };

  const handleSkip = () => {
    setError('');
    setSuccess('');
    if (activeStep === stepLabels.length - 1) {
      onClose();
      return;
    }
    setActiveStep((prev) => Math.min(prev + 1, stepLabels.length - 1));
  };

  const handleCreateAthlete = async () => {
    setError('');
    setSuccess('');
    if (!athleteForm.nombre.trim() || !athleteForm.apellido.trim()) {
      setError('Nombre y apellido son obligatorios.');
      return;
    }
    try {
      setCreatingAthlete(true);
      const res = await client.post('/api/alumnos/', {
        nombre: athleteForm.nombre.trim(),
        apellido: athleteForm.apellido.trim(),
        email: athleteForm.email.trim() || null,
      });
      setCreatedAthlete(res.data);
      setSuccess('Atleta creado correctamente.');
    } catch {
      setError('No se pudo crear el atleta. Intenta nuevamente.');
    } finally {
      setCreatingAthlete(false);
    }
  };

  const handleAssignTemplate = async () => {
    setError('');
    setSuccess('');
    if (!createdAthlete?.id) {
      setError('Primero crea un atleta para asignar una plantilla.');
      return;
    }
    if (!templateId) {
      setError('Selecciona una plantilla.');
      return;
    }
    try {
      setAssigningTemplate(true);
      await client.post(`/api/plantillas/${templateId}/asignar_a_alumno/`, {
        alumno_id: createdAthlete.id,
        fecha: templateDate,
      });
      setSuccess('Plantilla asignada correctamente.');
    } catch {
      setError('No se pudo asignar la plantilla. Revisa los datos e intenta otra vez.');
    } finally {
      setAssigningTemplate(false);
    }
  };

  const handleComplete = async () => {
    setError('');
    setSuccess('');
    try {
      setCompleting(true);
      await client.post('/api/onboarding/complete/');
      onComplete();
    } catch {
      setError('No pudimos guardar el progreso. Intenta nuevamente.');
    } finally {
      setCompleting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Asistente de Inicio para Coaches</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ mb: 3 }}>
          <Stepper activeStep={activeStep} alternativeLabel>
            {stepLabels.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        {activeStep === 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="h6">Conecta Strava en segundos</Typography>
            <Typography variant="body2" color="text.secondary">
              Sincroniza actividades para alimentar el PMC y alertas automáticas.
            </Typography>
            <Button
              variant="contained"
              color="primary"
              component="a"
              href="/accounts/strava/login/"
            >
              Conectar Strava
            </Button>
          </Box>
        )}

        {activeStep === 1 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="h6">Crea tu primer atleta</Typography>
            <Typography variant="body2" color="text.secondary">
              Solo necesitamos los datos mínimos para empezar.
            </Typography>
            <TextField
              label="Nombre"
              value={athleteForm.nombre}
              onChange={(e) => setAthleteForm((prev) => ({ ...prev, nombre: e.target.value }))}
              required
            />
            <TextField
              label="Apellido"
              value={athleteForm.apellido}
              onChange={(e) => setAthleteForm((prev) => ({ ...prev, apellido: e.target.value }))}
              required
            />
            <TextField
              label="Email (opcional)"
              value={athleteForm.email}
              onChange={(e) => setAthleteForm((prev) => ({ ...prev, email: e.target.value }))}
            />
            <Button
              variant="contained"
              onClick={handleCreateAthlete}
              disabled={creatingAthlete}
            >
              {creatingAthlete ? 'Creando...' : 'Crear atleta'}
            </Button>
            {createdAthlete && (
              <Typography variant="caption" color="text.secondary">
                Atleta listo: #{createdAthlete.id} {createdAthlete.nombre} {createdAthlete.apellido}
              </Typography>
            )}
          </Box>
        )}

        {activeStep === 2 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="h6">Asigna una plantilla</Typography>
            <Typography variant="body2" color="text.secondary">
              Selecciona una plantilla para tu nuevo atleta.
            </Typography>
            {templateOptions.length === 0 ? (
              <Alert severity="info">
                No encontramos plantillas. Puedes crearlas desde la biblioteca en{' '}
                <Link component={RouterLink} to="/teams" underline="hover">
                  equipos
                </Link>{' '}
                o{' '}
                <Link component={RouterLink} to="/athletes" underline="hover">
                  atletas
                </Link>
                .
              </Alert>
            ) : (
              <>
                <TextField
                  select
                  label="Plantilla"
                  value={templateId}
                  onChange={(e) => setTemplateId(String(e.target.value))}
                >
                  {templateOptions.map((t) => (
                    <MenuItem key={t.id} value={String(t.id)}>
                      {t.titulo} · {t.deporte} · {t.dificultad}
                    </MenuItem>
                  ))}
                </TextField>
                {templateId && (
                  <Typography variant="caption" color="text.secondary">
                    {templateOptions.find((t) => String(t.id) === templateId)?.descripcion || 'Sin descripción'}
                  </Typography>
                )}
                <TextField
                  label="Fecha de inicio"
                  type="date"
                  value={templateDate}
                  onChange={(e) => setTemplateDate(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                />
                <Button
                  variant="contained"
                  onClick={handleAssignTemplate}
                  disabled={assigningTemplate}
                >
                  {assigningTemplate ? 'Asignando...' : 'Asignar plantilla'}
                </Button>
              </>
            )}
          </Box>
        )}

        {activeStep === 3 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="h6">Tour rápido de PMC y Alertas</Typography>
            <Typography variant="body2" color="text.secondary">
              Un recorrido corto para ubicar las métricas clave del dashboard.
            </Typography>
            <Button variant="outlined" onClick={() => setRunTour(true)}>
              Iniciar tour
            </Button>
            <Joyride
              steps={joyrideSteps}
              run={runTour}
              continuous
              showSkipButton
              showProgress
              styles={{
                options: {
                  zIndex: 1400,
                },
              }}
              callback={(data) => {
                if (['finished', 'skipped'].includes(data.status)) {
                  setRunTour(false);
                }
              }}
            />
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button onClick={handleBack} disabled={activeStep === 0}>
          Volver
        </Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button onClick={handleSkip}>Saltar por ahora</Button>
          {activeStep < stepLabels.length - 1 ? (
            <Button variant="contained" onClick={handleNext}>
              Continuar
            </Button>
          ) : (
            <Button variant="contained" onClick={handleComplete} disabled={completing}>
              {completing ? 'Guardando...' : 'Finalizar onboarding'}
            </Button>
          )}
        </Box>
      </DialogActions>
      <Divider />
    </Dialog>
  );
}
