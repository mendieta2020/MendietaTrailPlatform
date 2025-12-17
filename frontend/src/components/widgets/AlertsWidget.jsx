import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert as MUIAlert,
  Box,
  Chip,
  CircularProgress,
  Divider,
  Pagination,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import client from '../../api/client';

function formatDate(isoOrDate) {
  try {
    // backend devuelve DateField (YYYY-MM-DD)
    const d = new Date(isoOrDate);
    if (Number.isNaN(d.getTime())) return String(isoOrDate || '');
    return d.toLocaleDateString();
  } catch {
    return String(isoOrDate || '');
  }
}

function tipoLabel(tipo) {
  if (tipo === 'FTP_UP') return 'FTP ↑';
  if (tipo === 'HR_MAX') return 'FC máx';
  return tipo;
}

export default function AlertsWidget({ pageSize = 20, initialPage = 1 }) {
  const [page, setPage] = useState(initialPage);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const pageCount = useMemo(() => Math.max(1, Math.ceil((count || 0) / pageSize)), [count, pageSize]);

  useEffect(() => {
    let cancelled = false;

    async function fetchAlerts() {
      try {
        setLoading(true);
        setError('');

        const resp = await client.get('/api/analytics/alerts/', {
          params: { page, page_size: pageSize },
        });

        if (cancelled) return;

        const data = resp.data;
        const results = Array.isArray(data?.results) ? data.results : [];

        setItems(results);
        setCount(typeof data?.count === 'number' ? data.count : results.length);
      } catch {
        if (cancelled) return;
        setError('No se pudieron cargar las alertas.');
        setItems([]);
        setCount(0);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAlerts();
    return () => {
      cancelled = true;
    };
  }, [page, pageSize]);

  return (
    <Paper sx={{ p: 3, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, mb: 2 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Alertas de rendimiento</Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Últimas detecciones automáticas (JWT + paginación opt-in).
          </Typography>
        </Box>
        {loading && <CircularProgress size={18} />}
      </Box>

      <Divider sx={{ mb: 2 }} />

      {error && <MUIAlert severity="error" sx={{ mb: 2 }}>{error}</MUIAlert>}

      {!error && !loading && items.length === 0 && (
        <MUIAlert severity="info">No hay alertas.</MUIAlert>
      )}

      <Stack spacing={1.5} sx={{ mb: 2 }}>
        {items.map((a) => (
          <Box key={a.id} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2 }}>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
                {a.mensaje}
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748B' }}>
                {formatDate(a.fecha)} · Alumno #{a.alumno}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} sx={{ flexShrink: 0, alignItems: 'center' }}>
              <Chip size="small" label={tipoLabel(a.tipo)} variant="outlined" />
              <Chip
                size="small"
                label={a.visto_por_coach ? 'Visto' : 'Nuevo'}
                color={a.visto_por_coach ? 'default' : 'warning'}
                variant={a.visto_por_coach ? 'outlined' : 'filled'}
              />
            </Stack>
          </Box>
        ))}
      </Stack>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
        <Typography variant="caption" sx={{ color: '#64748B' }}>
          {count} total
        </Typography>
        <Pagination
          size="small"
          page={page}
          count={pageCount}
          onChange={(_, p) => setPage(p)}
        />
      </Box>
    </Paper>
  );
}
