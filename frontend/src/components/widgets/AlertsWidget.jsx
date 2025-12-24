import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert as MUIAlert, Box, Button, Divider, Stack, Tooltip, Typography } from '@mui/material';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

import { getAlerts } from '../../api/endpoints/analytics';
import Card from '../ui/Card';
import Badge from '../ui/Badge';
import SegmentedControl from '../ui/SegmentedControl';
import SkeletonList from '../ui/Skeleton';
import StatPill from '../ui/StatPill';

function formatDate(isoOrDate) {
  try {
    // backend devuelve DateField (YYYY-MM-DD)
    const d = typeof isoOrDate === 'string' ? parseISO(isoOrDate) : new Date(isoOrDate);
    if (Number.isNaN(d.getTime())) return String(isoOrDate || '');
    return format(d, 'd MMM', { locale: es });
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

export default function AlertsWidget({ alumnoId, pageSize = 5 }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('open'); // open | seen
  const vistoPorCoach = useMemo(() => tab === 'seen', [tab]);
  const [retryTick, setRetryTick] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const ac = new AbortController();

    async function fetchAlerts() {
      try {
        setLoading(true);
        setError('');

        const data = await getAlerts({
          page: 1,
          pageSize,
          alumnoId,
          vistoPorCoach,
          signal: ac.signal,
        });

        const results = Array.isArray(data?.results) ? data.results : [];
        setItems(results);
        setCount(typeof data?.count === 'number' ? data.count : results.length);
      } catch (e) {
        // Abort: ignorar (evita race conditions al cambiar tabs / alumno)
        if (e?.name === 'CanceledError' || e?.name === 'AbortError') return;
        setError('No pudimos cargar las alertas. Probá de nuevo.');
        setItems([]);
        setCount(0);
      } finally {
        setLoading(false);
      }
    }

    fetchAlerts();
    return () => {
      ac.abort();
    };
  }, [alumnoId, pageSize, vistoPorCoach, retryTick]);

  const title = alumnoId ? `Alertas · Atleta #${alumnoId}` : 'Alertas';

  return (
    <Card>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, mb: 2 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 800, color: '#0F172A' }}>
            {title}
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Señales automáticas que valen una mirada hoy.
          </Typography>
        </Box>

        <SegmentedControl
          value={tab}
          onChange={setTab}
          options={[
            { value: 'open', label: 'Abiertas' },
            { value: 'seen', label: 'Vistas' },
          ]}
        />
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

      {!error && loading && <SkeletonList rows={pageSize} />}

      {!error && !loading && items.length === 0 && (
        <MUIAlert severity="info">
          {tab === 'open' ? 'No hay alertas abiertas.' : 'Todavía no hay alertas marcadas como vistas.'}
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
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 2,
                  p: 1.5,
                  borderRadius: 2,
                  border: '1px solid #E2E8F0',
                  bgcolor: 'white',
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                    <Badge label={tipoLabel(a.tipo)} tone="info" />
                    {!alumnoId && <Badge label={`Atleta #${a.alumno}`} tone="neutral" variant="outline" />}
                    {!a.visto_por_coach && <Badge label="Nuevo" tone="warning" />}
                    {values && <StatPill label={values} />}
                  </Box>

                  <Tooltip title={a.mensaje || ''} placement="top-start">
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        color: '#0F172A',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {a.mensaje}
                    </Typography>
                  </Tooltip>

                  <Typography variant="caption" sx={{ color: '#64748B' }}>
                    {formatDate(a.fecha)}
                  </Typography>
                </Box>

                <Box sx={{ flexShrink: 0, textAlign: 'right' }}>
                  <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700 }}>
                    #{a.id}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Stack>
      )}

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
        <Typography variant="caption" sx={{ color: '#64748B' }}>
          {loading ? 'Cargando…' : `${count} total`}
        </Typography>
        <Button
          variant="text"
          size="small"
          sx={{ fontWeight: 800, color: '#F57C00' }}
          onClick={() => {
            const params = new URLSearchParams();
            params.set('estado', tab);
            if (alumnoId) params.set('alumno_id', String(alumnoId));
            navigate(`/alerts?${params.toString()}`);
          }}
        >
          Ver todas
        </Button>
      </Box>
    </Card>
  );
}
