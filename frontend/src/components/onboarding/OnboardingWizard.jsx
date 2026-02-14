import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Popover,
  Select,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { format } from 'date-fns';
import client from '../../api/client';

const TOUR_TARGETS = [
  { id: 'pmc-widget', title: 'Rendimiento Fisiológico (PMC)' },
  { id: 'alerts-widget', title: 'Alertas y Riesgos' },
];

const OnboardingWizard = ({ open, onClose }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState('');
  const [athleteForm, setAthleteForm] = useState({ nombre: '', apellido: '', email: '' });
  const [athleteError, setAthleteError] = useState('');
  const [athleteSaving, setAthleteSaving] = useState(false);
  const [createdAthlete, setCreatedAthlete] = useState(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [assignError, setAssignError] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);
  const [completeSaving, setCompleteSaving] = useState(false);
  const [completeError, setCompleteError] = useState('');
  const [tourAnchor, setTourAnchor] = useState(null);
  const [tourTarget, setTourTarget] = useState(null);

  const steps = useMemo(
    () => [
      'Conecta Strava',
      'Crea tu primer atleta',
      'Asigna una plantilla',
      'Explora PMC y alertas',
      'Finaliza onboarding',
    ],
    []
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveStep(0);
    setAthleteError('');
    setAssignError('');
    setCompleteError('');
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const fetchTemplates = async () => {
      setTemplatesLoading(true);
      setTemplatesError('');
      try {
        const resp = await client.get('/api/plantillas/');
        const payload = resp.data?.results ?? resp.data ?? [];
        setTemplates(Array.isArray(payload) ? payload : []);
      } catch (err) {
        console.error('Onboarding templates error:', err);
        setTemplatesError('No se pudieron cargar las plantillas.');
      } finally {
        setTemplatesLoading(false);
      }
    };
    fetchTemplates();
  }, [open]);

  const handleNext = () => {
    setActiveStep((prev) => Math.min(prev + 1, steps.length - 1));
  };

  const handleBack = () => {
    setActiveStep((prev) => Math.max(prev - 1, 0));
  };

  const handleCreateAthlete = async () => {
    setAthleteError('');
    const nombre = athleteForm.nombre.trim();
    const apellido = athleteForm.apellido.trim();
    const email = athleteForm.email.trim();
    if (!nombre || !apellido) {
      setAthleteError('Nombre y apellido son obligatorios.');
      return;
    }
    setAthleteSaving(true);
    try {
      const resp = await client.post('/api/alumnos/', {
        nombre,
        apellido,
        email: email || null,
      });
      setCreatedAthlete(resp.data);
    } catch (err) {
      console.error('Onboarding create athlete error:', err);
      setAthleteError('No se pudo crear el atleta.');
    } finally {
      setAthleteSaving(false);
    }
  };

  const handleAssignTemplate = async () => {
    setAssignError('');
    if (!createdAthlete?.id) {
      setAssignError('Primero crea un atleta.');
      return;
    }
    if (!selectedTemplateId) {
      setAssignError('Selecciona una plantilla.');
      return;
    }
    setAssignSaving(true);
    try {
      const today = format(new Date(), 'yyyy-MM-dd');
      await client.post(`/api/plantillas/${selectedTemplateId}/asignar_a_alumno/`, {
        alumno_id: createdAthlete.id,
        fecha: today,
      });
    } catch (err) {
      console.error('Onboarding assign template error:', err);
      setAssignError('No se pudo asignar la plantilla.');
    } finally {
      setAssignSaving(false);
    }
  };

  const handleComplete = async () => {
    setCompleteError('');
    setCompleteSaving(true);
    try {
      await client.post('/api/onboarding/complete/');
      onClose?.();
    } catch (err) {
      console.error('Onboarding complete error:', err);
      setCompleteError('No se pudo finalizar el onboarding.');
    } finally {
      setCompleteSaving(false);
    }
  };

  const handleOpenTourTarget = (target) => {
    const element = document.getElementById(target.id);
    if (!element) {
      setTourTarget({ ...target, missing: true });
      setTourAnchor(document.body);
      return;
    }
    setTourTarget({ ...target, missing: false });
    setTourAnchor(element);
  };

  const handleCloseTour = () => {
    setTourAnchor(null);
    setTourTarget(null);
  };

  const renderStepContent = () => {
    switch (activeStep) {
      case 0:
        return (
          <Stack spacing={2}>
            <Typography>
              Conecta Strava para importar actividades y activar métricas científicas.
            </Typography>
            <Button
              variant="contained"
              color="primary"
              href="/accounts/strava/login/"
            >
              Conectar con Strava
            </Button>
            <Alert severity="info">
              Puedes continuar sin conectar ahora; el flujo no se bloquea.
            </Alert>
          </Stack>
        );
      case 1:
        return (
          <Stack spacing={2}>
            <Typography>Registra tu primer atleta para empezar a planificar.</Typography>
            <TextField
              label="Nombre"
              value={athleteForm.nombre}
              onChange={(event) =>
                setAthleteForm((prev) => ({ ...prev, nombre: event.target.value }))
              }
            />
            <TextField
              label="Apellido"
              value={athleteForm.apellido}
              onChange={(event) =>
                setAthleteForm((prev) => ({ ...prev, apellido: event.target.value }))
              }
            />
            <TextField
              label="Email (opcional)"
              type="email"
              value={athleteForm.email}
              onChange={(event) =>
                setAthleteForm((prev) => ({ ...prev, email: event.target.value }))
              }
            />
            {athleteError && <Alert severity="error">{athleteError}</Alert>}
            {createdAthlete && (
              <Alert severity="success">
                Atleta creado: {createdAthlete.nombre} {createdAthlete.apellido}
              </Alert>
            )}
            <Box>
              <Button
                variant="contained"
                onClick={handleCreateAthlete}
                disabled={athleteSaving}
              >
                {athleteSaving ? <CircularProgress size={20} /> : 'Crear atleta'}
              </Button>
            </Box>
          </Stack>
        );
      case 2:
        return (
          <Stack spacing={2}>
            <Typography>Asigna una plantilla para generar el primer plan.</Typography>
            {templatesLoading ? (
              <CircularProgress size={24} />
            ) : (
              <FormControl fullWidth>
                <InputLabel>Plantilla</InputLabel>
                <Select
                  value={selectedTemplateId}
                  label="Plantilla"
                  onChange={(event) => setSelectedTemplateId(event.target.value)}
                >
                  {templates.map((template) => (
                    <MenuItem key={template.id} value={template.id}>
                      {template.titulo}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
            {templatesError && <Alert severity="warning">{templatesError}</Alert>}
            {assignError && <Alert severity="error">{assignError}</Alert>}
            <Box>
              <Button
                variant="contained"
                onClick={handleAssignTemplate}
                disabled={assignSaving}
              >
                {assignSaving ? <CircularProgress size={20} /> : 'Asignar plantilla'}
              </Button>
            </Box>
            {!createdAthlete && (
              <Alert severity="info">Puedes crear el atleta en el paso anterior.</Alert>
            )}
          </Stack>
        );
      case 3:
        return (
          <Stack spacing={2}>
            <Typography>
              Revisa el widget PMC y las alertas para entender el estado del equipo.
            </Typography>
            <Divider />
            <Stack direction="row" spacing={2} flexWrap="wrap">
              {TOUR_TARGETS.map((target) => (
                <Button
                  key={target.id}
                  variant="outlined"
                  onClick={() => handleOpenTourTarget(target)}
                >
                  Ver {target.title}
                </Button>
              ))}
            </Stack>
            <Alert severity="info">
              Si un widget no está visible, te mostraremos un resumen aquí mismo.
            </Alert>
          </Stack>
        );
      case 4:
        return (
          <Stack spacing={2}>
            <Typography>¡Listo! Marca el onboarding como completo.</Typography>
            {completeError && <Alert severity="error">{completeError}</Alert>}
            <Button
              variant="contained"
              onClick={handleComplete}
              disabled={completeSaving}
            >
              {completeSaving ? <CircularProgress size={20} /> : 'Finalizar'}
            </Button>
          </Stack>
        );
      default:
        return null;
    }
  };

  const popoverOpen = Boolean(tourTarget);

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Onboarding inicial</DialogTitle>
        <DialogContent dividers>
          <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 3 }}>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
          {renderStepContent()}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cerrar</Button>
          <Button onClick={handleBack} disabled={activeStep === 0}>
            Atrás
          </Button>
          <Button onClick={handleNext} disabled={activeStep === steps.length - 1}>
            Siguiente
          </Button>
        </DialogActions>
      </Dialog>
      <Popover
        open={popoverOpen}
        anchorEl={tourAnchor}
        onClose={handleCloseTour}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        transformOrigin={{ vertical: 'top', horizontal: 'center' }}
      >
        <Box sx={{ p: 2, maxWidth: 320 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
            {tourTarget?.title}
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {tourTarget?.id === 'pmc-widget'
              ? 'Aquí ves la evolución de carga, fitness y fatiga.'
              : 'Revisa alertas críticas y señales de riesgo.'}
          </Typography>
          {tourTarget?.missing && (
            <Alert severity="warning">Widget no encontrado. Usa el Dashboard para verlo.</Alert>
          )}
          <Box sx={{ mt: 2, textAlign: 'right' }}>
            <Button size="small" onClick={handleCloseTour}>
              Entendido
            </Button>
          </Box>
        </Box>
      </Popover>
    </>
  );
};

export default OnboardingWizard;
