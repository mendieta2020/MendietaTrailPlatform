import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert as MUIAlert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import Layout from '../components/Layout';
import client from '../api/client';

function formatDate(isoOrDate) {
  try {
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
  return String(tipo || '');
}

function normalizeTags(tags) {
  if (!tags) return [];
  if (Array.isArray(tags)) return tags.filter(Boolean).map(String);
  return [String(tags)];
}

export default function Alerts() {
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil((count || 0) / pageSize)),
    [count, pageSize]
  );

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
      } catch (err) {
        if (cancelled) return;
        console.error('Error cargando alertas:', err);
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
    <Layout>
      <Card sx={{ borderRadius: 3, boxShadow: '0 4px 18px rgba(0,0,0,0.04)' }}>
        <CardContent sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, mb: 1 }}>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A' }}>
                Alertas
              </Typography>
              <Typography variant="body2" sx={{ color: '#64748B' }}>
                Listado de alertas detectadas automáticamente.
              </Typography>
            </Box>
            {loading && <CircularProgress size={18} />}
          </Box>

          <Divider sx={{ my: 2 }} />

          {error && <MUIAlert severity="error">{error}</MUIAlert>}

          {!error && !loading && items.length === 0 && (
            <MUIAlert severity="info">No hay alertas para mostrar.</MUIAlert>
          )}

          {!error && items.length > 0 && (
            <TableContainer>
              <Table size="small" aria-label="Tabla de alertas">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 800 }}>Fecha</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>Alumno</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>Tipo</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>Mensaje</TableCell>
                    <TableCell sx={{ fontWeight: 800, whiteSpace: 'nowrap' }}>Visto</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>Tags</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((a) => {
                    const tags = normalizeTags(a.tags);
                    const alumnoLabel = a.alumno_nombre || a.alumno_name || a.alumno || '—';
                    return (
                      <TableRow key={a.id} hover>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(a.fecha)}</TableCell>
                        <TableCell>{alumnoLabel}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>
                          <Chip size="small" variant="outlined" label={tipoLabel(a.tipo)} />
                        </TableCell>
                        <TableCell sx={{ minWidth: 260 }}>{a.mensaje || '—'}</TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={a.visto_por_coach ? 'Visto' : 'Nuevo'}
                            color={a.visto_por_coach ? 'default' : 'warning'}
                            variant={a.visto_por_coach ? 'outlined' : 'filled'}
                          />
                        </TableCell>
                        <TableCell>
                          {tags.length === 0 ? (
                            <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                              —
                            </Typography>
                          ) : (
                            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                              {tags.map((t) => (
                                <Chip key={`${a.id}:${t}`} size="small" label={t} variant="outlined" />
                              ))}
                            </Stack>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, mt: 2 }}>
            <Typography variant="caption" sx={{ color: '#64748B' }}>
              {count} total
            </Typography>
            <Pagination size="small" page={page} count={pageCount} onChange={(_, p) => setPage(p)} />
          </Box>
        </CardContent>
      </Card>
    </Layout>
  );
}

