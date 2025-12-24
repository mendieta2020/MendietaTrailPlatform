import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert as MUIAlert,
  Box,
  Button,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Pagination,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import Layout from '../components/Layout';
import Card from '../components/ui/Card';
import SegmentedControl from '../components/ui/SegmentedControl';
import Badge from '../components/ui/Badge';
import SkeletonList from '../components/ui/Skeleton';
import StatPill from '../components/ui/StatPill';
import client from '../api/client';
import { getAlerts } from '../api/endpoints/analytics';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

function formatDate(isoOrDate) {
  try {
    const d = typeof isoOrDate === 'string' ? parseISO(isoOrDate) : new Date(isoOrDate);
    if (Number.isNaN(d.getTime())) return String(isoOrDate || '');
    return format(d, 'PP', { locale: es });
  } catch {
    return String(isoOrDate || '');
  }
}

function tipoLabel(tipo) {
  if (tipo === 'FTP_UP') return 'FTP ↑';
  if (tipo === 'HR_MAX') return 'FC máx';
  return tipo;
}

function valuesLabel(a) {
  const prev = a?.valor_anterior;
  const next = a?.valor_detectado;
  if (prev === null || prev === undefined || prev === '' || next === null || next === undefined || next === '') return null;
  return `${prev} → ${next}`;
}

export default function AlertsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const initialEstado = searchParams.get('estado') === 'seen' ? 'seen' : 'open';
  const initialAlumnoId = searchParams.get('alumno_id') || '';

  const [estado, setEstado] = useState(initialEstado); // open|seen
  const [alumnoId, setAlumnoId] = useState(initialAlumnoId);

  const vistoPorCoach = useMemo(() => estado === 'seen', [estado]);

  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [retryTick, setRetryTick] = useState(0);

  const [athletes, setAthletes] = useState([]);
  const [athletesError, setAthletesError] = useState('');

  const pageCount = useMemo(() => Math.max(1, Math.ceil((count || 0) / pageSize)), [count, pageSize]);

  // Keep URL in sync (shallow)
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set('estado', estado);
    if (alumnoId) next.set('alumno_id', String(alumnoId));
    else next.delete('alumno_id');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, alumnoId]);

  // Load athletes for dropdown (best-effort)
  useEffect(() => {
    const ac = new AbortController();

    async function loadAthletes() {
      try {
        setAthletesError('');
        const resp = await client.get('/api/alumnos/', { signal: ac.signal });
        const list = Array.isArray(resp.data) ? resp.data : [];
        setAthletes(list);
      } catch (e) {
        if (e?.name === 'CanceledError' || e?.name === 'AbortError') return;
        setAthletes([]);
        setAthletesError('No pudimos cargar la lista de atletas. Podés filtrar por ID.');
      }
    }

    loadAthletes();
    return () => ac.abort();
  }, []);

  // Load alerts
  useEffect(() => {
    const ac = new AbortController();

    async function load() {
      try {
        setLoading(true);
        setError('');

        const data = await getAlerts({
          page,
          pageSize,
          alumnoId: alumnoId ? Number(alumnoId) : undefined,
          vistoPorCoach,
          signal: ac.signal,
        });

        const results = Array.isArray(data?.results) ? data.results : [];
        setItems(results);
        setCount(typeof data?.count === 'number' ? data.count : results.length);
      } catch (e) {
        if (e?.name === 'CanceledError' || e?.name === 'AbortError') return;
        setError('No pudimos cargar las alertas. Revisá tu conexión e intentá de nuevo.');
        setItems([]);
        setCount(0);
      } finally {
        setLoading(false);
      }
    }

    load();
    return () => ac.abort();
  }, [page, pageSize, alumnoId, vistoPorCoach, retryTick]);

  // Reset to first page when filters change
  useEffect(() => {
    setPage(1);
  }, [estado, alumnoId]);

  const athleteOptions = useMemo(
    () =>
      athletes.map((a) => ({
        id: a.id,
        label: `${a.nombre || ''} ${a.apellido || ''}`.trim() || `Atleta #${a.id}`,
      })),
    [athletes]
  );

  return (
    <Layout>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A' }}>
            Alertas
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Lista completa con filtros: abrí la señal, mirá el contexto y actuá.
          </Typography>
        </Box>
      </Box>

      <Card sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <SegmentedControl
            value={estado}
            onChange={setEstado}
            options={[
              { value: 'open', label: 'Abiertas' },
              { value: 'seen', label: 'Vistas' },
            ]}
          />

          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <FormControl size="small" sx={{ minWidth: 220, bgcolor: 'white' }}>
              <InputLabel>Atleta</InputLabel>
              <Select
                label="Atleta"
                value={alumnoId ? String(alumnoId) : ''}
                onChange={(e) => setAlumnoId(e.target.value)}
              >
                <MenuItem value="">
                  <em>Todos</em>
                </MenuItem>
                {athleteOptions.map((opt) => (
                  <MenuItem key={opt.id} value={String(opt.id)}>
                    {opt.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Fallback: si no hay listado, permitimos filtrar por ID manualmente */}
            {athletes.length === 0 && (
              <TextField
                size="small"
                label="ID (opcional)"
                value={alumnoId}
                onChange={(e) => setAlumnoId(e.target.value.replace(/[^\d]/g, ''))}
                sx={{ width: 140, bgcolor: 'white' }}
              />
            )}
          </Stack>
        </Box>

        {athletesError && (
          <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 1 }}>
            {athletesError}
          </Typography>
        )}
      </Card>

      <Card>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, mb: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0F172A' }}>
            Resultados
          </Typography>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            {loading ? 'Cargando…' : `${count} total`}
          </Typography>
        </Box>

        <Divider sx={{ mb: 2 }} />

        {error && (
          <MUIAlert
            severity="error"
            sx={{ mb: 2 }}
            action={
              <Button color="inherit" size="small" onClick={() => setRetryTick((x) => x + 1)}>
                Reintentar
              </Button>
            }
          >
            {error}
          </MUIAlert>
        )}

        {!error && loading && <SkeletonList rows={8} />}

        {!error && !loading && items.length === 0 && (
          <MUIAlert severity="info">
            {estado === 'open'
              ? 'No hay alertas abiertas para este filtro.'
              : 'No hay alertas vistas para este filtro.'}
          </MUIAlert>
        )}

        {!error && !loading && items.length > 0 && (
          <Stack spacing={1.5} sx={{ mb: 2 }}>
            {items.map((a) => {
              const values = valuesLabel(a);
              return (
                <Box
                  key={a.id}
                  sx={{
                    p: 2,
                    borderRadius: 2,
                    border: '1px solid #E2E8F0',
                    bgcolor: 'white',
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, alignItems: 'flex-start' }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.75 }}>
                        <Badge label={tipoLabel(a.tipo)} tone="info" />
                        <Badge label={`Atleta #${a.alumno}`} tone="neutral" variant="outline" />
                        {!a.visto_por_coach && <Badge label="Nuevo" tone="warning" />}
                        {values && <StatPill label={values} />}
                      </Box>

                      <Typography variant="body1" sx={{ fontWeight: 800, color: '#0F172A', mb: 0.5 }}>
                        {a.mensaje}
                      </Typography>

                      <Typography variant="caption" sx={{ color: '#64748B' }}>
                        {formatDate(a.fecha)} · #{a.id}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Stack>
        )}

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            Página {page} de {pageCount}
          </Typography>
          <Pagination size="small" page={page} count={pageCount} onChange={(_, p) => setPage(p)} />
        </Box>
      </Card>
    </Layout>
  );
}

