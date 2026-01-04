import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { 
  ComposedChart, Area, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  Legend, ReferenceLine, ReferenceArea, Cell, Brush 
} from 'recharts';
import { 
    Box, Paper, Typography, CircularProgress, Chip, MenuItem, Select, FormControl, 
    ToggleButton, ToggleButtonGroup, Stack, Divider, Grid
} from '@mui/material';
import { 
    AutoGraph, Flag, Timer, Terrain, Straighten, DirectionsRun, PedalBike, 
    Layers, LocalFireDepartment, EmojiEvents
} from '@mui/icons-material';
import client from '../../api/client';
import { format, parseISO, addMonths, subMonths, isValid, differenceInWeeks, startOfISOWeek, endOfISOWeek, getISOWeek, getISOWeekYear } from 'date-fns';
import { es } from 'date-fns/locale';

// --- COLORES PROFESIONALES ---
const COLORS = {
    FITNESS: '#2563EB',    
    FATIGUE: '#DB2777',    
    FORM: '#EAB308',       
    BAR_REAL: '#06B6D4',   
    BAR_PLAN: '#CFFAFE',   
    TIME_REAL: '#F59E0B',  
    TIME_PLAN: '#FEF3C7',  
    ELEV_POS: '#7C3AED',   
    ELEV_NEG: '#EF4444',   
    CALORIES: '#FF8C00',
    TODAY_LINE: '#EF4444',
    GRID: '#F1F5F9',
    TOOLTIP_BG: 'rgba(15, 23, 42, 0.98)'
};

const METRICS = {
    PERFORMANCE: { label: 'Performance (PMC)', icon: <AutoGraph fontSize="small"/> },
    DISTANCE: { label: 'Distancia', icon: <Straighten fontSize="small"/> },
    TIME: { label: 'Duración + Kcal', icon: <Timer fontSize="small"/> },
    ELEVATION: { label: 'Desnivel (+/-)', icon: <Terrain fontSize="small"/> },
};

const formatDurationHuman = (minutesLike) => {
    const totalMin = Math.max(0, Math.round(Number(minutesLike) || 0));
    const hrs = Math.floor(totalMin / 60);
    const mins = totalMin % 60;
    if (hrs <= 0) return `${mins} min`;
    return `${hrs} horas ${String(mins).padStart(2, '0')} min`;
};

const isoWeekKey = (d) => {
    try {
        const y = getISOWeekYear(d);
        const w = getISOWeek(d);
        return `${y}-${String(w).padStart(2, '0')}`;
    } catch {
        return '';
    }
};

// Helper seguro para fechas
const safeFormat = (dateStr, formatStr) => {
    try {
        if (!dateStr) return '';
        const date = parseISO(dateStr);
        return isValid(date) ? format(date, formatStr, { locale: es }) : '';
    } catch { return ''; }
};

const StudentPerformanceChart = ({ alumnoId, weeklyStats, granularity, onMetricChange, onRequireDaily, refreshNonce } = {}) => {
    // Cache por deporte para evitar mezcla al alternar RUN/BIKE/ALL
    const [dataBySport, setDataBySport] = useState({ ALL: [], RUN: [], BIKE: [] });
    const [loading, setLoading] = useState(true);
    const [metric, setMetric] = useState('PERFORMANCE');
    const [sport, setSport] = useState('ALL'); 
    const [range, setRange] = useState('SEASON');

    const chartWrapRef = useRef(null);
    // Default fijo para evitar width inválido en el primer render
    const [chartWidth, setChartWidth] = useState(900);

    const safeWeeklyStats = Array.isArray(weeklyStats) ? weeklyStats : [];
    const hasWeeklyStats = safeWeeklyStats.length > 0;
    const isWeekly = String(granularity || 'DAILY').toUpperCase() === 'WEEKLY';

    useEffect(() => {
        onMetricChange?.(metric);
    }, [metric, onMetricChange]);

    useEffect(() => {
        if (isWeekly && metric === 'PERFORMANCE') {
            onRequireDaily?.();
        }
    }, [isWeekly, metric, onRequireDaily]);

    useLayoutEffect(() => {
        const el = chartWrapRef.current;
        if (!el) return;

        const ro = new ResizeObserver((entries) => {
            const w = Math.floor(entries?.[0]?.contentRect?.width || 0);
            // Evita negativos / 0 intermitentes que rompen Recharts
            if (w > 0) setChartWidth(Math.max(320, w));
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    useEffect(() => {
        if (isWeekly) {
            // Debug visual solicitado: verificar payload semanal antes de dibujar
            // eslint-disable-next-line no-console
            console.log('Métrica Semanal:', safeWeeklyStats[0]);
        }
    }, [isWeekly, safeWeeklyStats]);

    useEffect(() => {
        let isMounted = true;
        const fetchData = async () => {
            try {
                setLoading(true);
                const params = new URLSearchParams();
                if (sport) params.set('sport', sport);
                if (alumnoId) params.set('alumno_id', String(alumnoId));
                const qs = params.toString();
                const res = await client.get(qs ? `/api/analytics/pmc/?${qs}` : `/api/analytics/pmc/`);
                if (isMounted) {
                    if (Array.isArray(res.data)) {
                        const sanitizedData = res.data.map(item => ({
                            ...item,
                            load: Number(item.load) || 0,
                            dist: Number(item.dist) || 0,
                            time: Number(item.time) || 0,
                            elev_gain: Number(item.elev_gain) || 0,
                            elev_loss_plot: item.elev_loss != null ? (Number(item.elev_loss) * -1) : null,
                            elev_loss_raw: item.elev_loss != null ? Number(item.elev_loss) : null,
                            calories: item.calories != null ? Number(item.calories) : null,
                            effort: item.effort != null ? Number(item.effort) : null,
                            ctl: Number(item.ctl) || 0,
                            atl: Number(item.atl) || 0,
                            tsb: Number(item.tsb) || 0,
                            fecha: item.fecha
                        }));
                        const key = String(sport || 'ALL').toUpperCase();
                        setDataBySport((prev) => ({ ...prev, [key]: sanitizedData }));
                    } else {
                        const key = String(sport || 'ALL').toUpperCase();
                        setDataBySport((prev) => ({ ...prev, [key]: [] }));
                    }
                }
            } catch (err) {
                console.error("Error PMC:", err);
                if (isMounted) {
                    const key = String(sport || 'ALL').toUpperCase();
                    setDataBySport((prev) => ({ ...prev, [key]: [] }));
                }
            } finally {
                if (isMounted) setLoading(false);
            }
        };
        fetchData();
        return () => { isMounted = false; };
    }, [sport, alumnoId, refreshNonce]);

    const currentDaily = Array.isArray(dataBySport?.[String(sport || 'ALL').toUpperCase()])
        ? dataBySport[String(sport || 'ALL').toUpperCase()]
        : [];

    // Filtrado de Datos
    const getFilteredData = () => {
        if (!currentDaily.length) return [];
        const today = new Date();
        let startDate, endDate;

        switch (range) {
            case '3M': startDate = subMonths(today, 3); endDate = addMonths(today, 1); break;
            case 'SEASON': startDate = subMonths(today, 6); endDate = addMonths(today, 6); break;
            case '1Y': startDate = subMonths(today, 12); endDate = addMonths(today, 6); break;
            default: startDate = subMonths(today, 6); endDate = addMonths(today, 6);
        }
        
        return currentDaily.filter(d => {
            const dDate = parseISO(d.fecha);
            return isValid(dDate) && dDate >= startDate && dDate <= endDate;
        });
    };

    const filteredData = getFilteredData();

    // Agregación semanal en frontend (estricta por deporte), construida desde el dataset diario ya filtrado por sport.
    const buildWeeklyFromDaily = () => {
        if (!filteredData.length) return [];
        const byWeek = new Map();

        for (const row of filteredData) {
            if (row.is_future) continue;
            if (!row.fecha) continue;
            let d;
            try {
                d = parseISO(row.fecha);
            } catch {
                continue;
            }
            if (!isValid(d)) continue;

            const wk = isoWeekKey(d);
            if (!wk) continue;
            const start = startOfISOWeek(d);
            const end = endOfISOWeek(d);

            const prev = byWeek.get(wk) || {
                week: wk,
                range_start: start.toISOString().slice(0, 10),
                range_end: end.toISOString().slice(0, 10),
                km: 0,
                elev_gain_m: 0,
                calories_kcal: 0,
                time_min: 0,
                load_sum: 0,
            };

            prev.km += Number(row.dist) || 0;
            prev.elev_gain_m += Number(row.elev_gain) || 0;
            prev.time_min += Number(row.time) || 0;
            prev.load_sum += Number(row.load) || 0;
            // Si calorías vienen null, se suman como 0 (mantiene comportamiento estable)
            prev.calories_kcal += Number(row.calories) || 0;

            byWeek.set(wk, prev);
        }

        const out = Array.from(byWeek.values())
            .map((w) => ({
                ...w,
                km: Math.round((Number(w.km) || 0) * 100) / 100,
                elev_gain_m: Math.round(Number(w.elev_gain_m) || 0),
                time_min: Math.round(Number(w.time_min) || 0),
                load_sum: Math.round(Number(w.load_sum) || 0),
                calories_kcal: Math.round(Number(w.calories_kcal) || 0),
            }))
            .sort((a, b) => String(a.week).localeCompare(String(b.week)));

        return out;
    };

    const weeklyFromDaily = buildWeeklyFromDaily();

    const getFilteredWeeklyData = () => {
        if (!hasWeeklyStats) return [];
        const today = new Date();
        let startDate, endDate;

        switch (range) {
            case '3M': startDate = subMonths(today, 3); endDate = addMonths(today, 1); break;
            case 'SEASON': startDate = subMonths(today, 6); endDate = addMonths(today, 6); break;
            case '1Y': startDate = subMonths(today, 12); endDate = addMonths(today, 6); break;
            default: startDate = subMonths(today, 6); endDate = addMonths(today, 6);
        }

        const mapped = safeWeeklyStats
            .map((w) => ({
                week: w?.week,
                range_start: w?.range?.start,
                range_end: w?.range?.end,
                km: Number(w?.km) || 0,
                elev_gain_m: Math.round(Number(w?.elev_gain_m) || 0),
                calories_kcal: Math.round(Number(w?.calories_kcal) || 0),
                // Si el backend agrega duración semanal en el futuro, la mostramos; si no, 0 (no rompe).
                time_min: Math.round(Number(w?.time_min ?? w?.duration_min ?? w?.duration ?? 0) || 0),
            }))
            .filter((w) => w.week && w.range_end);

        mapped.sort((a, b) => {
            try {
                return parseISO(a.range_end).getTime() - parseISO(b.range_end).getTime();
            } catch {
                return String(a.week).localeCompare(String(b.week));
            }
        });

        return mapped.filter((w) => {
            try {
                const d = parseISO(w.range_end);
                return isValid(d) && d >= startDate && d <= endDate;
            } catch {
                return false;
            }
        });
    };

    const filteredWeeklyData = getFilteredWeeklyData();
    const races = filteredData.filter(d => d.race);
    const todayStr = new Date().toISOString().split('T')[0];

    // En semanal, calculamos duración semanal desde datos diarios (PMC) para evitar 0
    const weeklyChartData = isWeekly ? weeklyFromDaily : [];
    
    // Próximo objetivo
    let nextRace = null, weeksToRace = null;
    if (races.length > 0) {
        nextRace = races.find(r => r.fecha >= todayStr);
        if (nextRace) weeksToRace = differenceInWeeks(parseISO(nextRace.fecha), new Date());
    }

    // Calculamos índice de inicio para Brush
    const startIndex = filteredData.length > 60 ? filteredData.length - 60 : 0;

    if (loading) return <Paper elevation={0} sx={{ p: 4, display:'flex', justifyContent:'center', borderRadius: 3, height: 500, border: '1px solid #E2E8F0' }}><CircularProgress /></Paper>;

    // En semanal, dependemos del dataset diario ya filtrado por sport.
    // Evita pantalla en blanco: mostramos "sin datos" por deporte si no hay.
    if (isWeekly && !weeklyChartData.length) {
        return (
            <Paper elevation={0} sx={{ p: 4, borderRadius: 3, height: 500, border: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'center', gap: 1 }}>
                <AutoGraph sx={{ fontSize: 60, color: '#CBD5E1', mb: 1 }} />
                <Typography color="textSecondary" fontWeight="bold">Sin datos de este deporte</Typography>
            </Paper>
        );
    }
    
    if (isWeekly && metric === 'PERFORMANCE') {
        return (
            <Paper elevation={0} sx={{ p: 4, textAlign:'center', borderRadius: 3, height: 500, border: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'center' }}>
                <AutoGraph sx={{ fontSize: 60, color: '#CBD5E1', mb: 2 }} />
                <Typography color="textSecondary" fontWeight="bold">Sin datos</Typography>
                <Typography variant="caption" color="textSecondary">La vista semanal aplica a Km/Desnivel/Kcal.</Typography>
            </Paper>
        );
    }

    // Estado vacío seguro (sin pantalla en blanco)
    if ((!isWeekly && !filteredData.length) || (isWeekly && !weeklyChartData.length)) {
        return (
            <Paper elevation={0} sx={{ p: 4, textAlign:'center', borderRadius: 3, height: 500, border: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'center' }}>
                <AutoGraph sx={{ fontSize: 60, color: '#CBD5E1', mb: 2 }} />
                <Typography color="textSecondary" fontWeight="bold">
                    {sport === 'ALL' ? 'Sin datos' : 'Sin datos de este deporte'}
                </Typography>
            </Paper>
        );
    }

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length && label) {
            const dayData = currentDaily.find(d => d.fecha === label);
            if (!dayData) return null;
            const isFut = dayData.is_future;
            const primaryLabel =
                metric === 'DISTANCE' ? 'Distancia (km)' :
                metric === 'TIME' ? 'Duración (min)' :
                metric === 'ELEVATION' ? 'Desnivel Positivo (m)' :
                'Valor';
            const primaryValue =
                metric === 'DISTANCE' ? dayData.dist :
                metric === 'TIME' ? dayData.time :
                metric === 'ELEVATION' ? dayData.elev_gain :
                (payload?.[0]?.value ?? null);
            
            return (
                <Paper sx={{ p: 2, bgcolor: COLORS.TOOLTIP_BG, color: 'white', borderRadius: 2, minWidth: 240, boxShadow: '0 8px 32px rgba(0,0,0,0.5)', zIndex: 9999 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, borderBottom: '1px solid rgba(255,255,255,0.2)', pb: 1 }}>
                        <Typography variant="subtitle2" fontWeight={700}>
                            {safeFormat(label, 'EEEE d MMM')}
                        </Typography>
                        {isFut && <Chip label="PLAN" size="small" sx={{ ml: 1, height: 18, fontSize: '0.6rem', bgcolor:'rgba(255,255,255,0.2)', color:'white' }} />}
                    </Box>
                    {dayData.race && (
                        <Box sx={{ mb: 2, p: 1, bgcolor: 'rgba(239, 68, 68, 0.2)', border: '1px solid #EF4444', borderRadius: 1, display:'flex', gap:1, alignItems:'center' }}>
                             <Flag sx={{ color: '#EF4444', fontSize: 16 }} />
                             <Typography variant="caption" fontWeight="bold" color="#FCA5A5">OBJETIVO</Typography>
                             <Typography variant="caption" sx={{ ml:'auto', color:'white' }}>{dayData.race.nombre}</Typography>
                        </Box>
                    )}
                    <Stack spacing={0.5}>
                        {metric === 'PERFORMANCE' ? (
                           <><DataRow color={COLORS.FITNESS} label="Fitness" value={dayData.ctl} /><DataRow color={COLORS.FATIGUE} label="Fatiga" value={dayData.atl} /><DataRow color={COLORS.FORM} label="Forma" value={dayData.tsb} /></>
                        ) : (
                          <DataRow color="#fff" label={primaryLabel} value={primaryValue} />
                        )}
                        <Divider sx={{ my: 1, borderColor: 'rgba(255,255,255,0.1)' }} />
                        {metric === 'TIME' && (
                          <>
                            <DataRow
                              icon={<Timer fontSize="inherit" />}
                              label="Duración"
                              value={formatDurationHuman(dayData.time)}
                              color="rgba(255,255,255,0.85)"
                            />
                            <DataRow
                              icon={<LocalFireDepartment fontSize="inherit"/>}
                              label="Calorías"
                              value={`${Math.round(Number(dayData.calories) || 0)} kcal`}
                              color={COLORS.CALORIES}
                            />
                            <DataRow
                              icon={<Layers fontSize="inherit" />}
                              label="Esfuerzo total"
                              value={Math.round(Number(dayData.load) || 0)}
                              color="rgba(255,255,255,0.85)"
                            />
                          </>
                        )}
                        {/* Eliminamos duplicidad: en TIME mostramos sólo load como Esfuerzo */}
                        {(dayData.elev_gain > 0 || dayData.elev_loss_raw != null) && (
                          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'space-between' }}>
                            {dayData.elev_gain > 0 && (
                              <Typography variant="caption" sx={{ color: '#A78BFA' }}>
                                ▲ {dayData.elev_gain}m
                              </Typography>
                            )}
                            {dayData.elev_loss_raw != null && (
                              <Typography variant="caption" sx={{ color: '#F87171' }}>
                                ▼ {dayData.elev_loss_raw}m
                              </Typography>
                            )}
                          </Box>
                        )}
                    </Stack>
                </Paper>
            );
        }
        return null;
    };

    const WeeklyTooltip = ({ active, payload, label }) => {
        if (!active || !payload || !payload.length) return null;
        const p = payload[0]?.payload || {};
        const weekLabel = label || p.week;
        const kcal = Math.round(Number(p.calories_kcal) || 0);
        const tmin = Math.round(Number(p.time_min) || 0);
        const km = Number(p.km) || 0;
        const elev = Math.round(Number(p.elev_gain_m) || 0);
        const loadSum = Math.round(Number(p.load_sum) || 0);

        return (
            <Paper sx={{ p: 2, bgcolor: COLORS.TOOLTIP_BG, color: 'white', borderRadius: 2, minWidth: 240, boxShadow: '0 8px 32px rgba(0,0,0,0.5)', zIndex: 9999 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, borderBottom: '1px solid rgba(255,255,255,0.2)', pb: 1 }}>
                    <Typography variant="subtitle2" fontWeight={700}>
                        {String(weekLabel || '')}
                    </Typography>
                    <Chip label="SEMANA" size="small" sx={{ ml: 1, height: 18, fontSize: '0.6rem', bgcolor:'rgba(255,255,255,0.2)', color:'white' }} />
                </Box>
                <Stack spacing={0.75}>
                    {metric === 'TIME' && (
                        <>
                          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
                              Duración: <strong>{formatDurationHuman(tmin)}</strong>
                          </Typography>
                          <Typography variant="caption" sx={{ color: COLORS.CALORIES, opacity: 0.95 }}>
                              Calorías: <strong>{kcal} kcal</strong>
                          </Typography>
                          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
                              Esfuerzo total: <strong>{loadSum}</strong>
                          </Typography>
                        </>
                    )}
                    {metric === 'DISTANCE' && (
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
                            Total Semanal: <strong>{km} km</strong>
                        </Typography>
                    )}
                    {metric === 'ELEVATION' && (
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.85)' }}>
                            Total Semanal: <strong>{elev} m+</strong>
                        </Typography>
                    )}
                </Stack>
            </Paper>
        );
    };

    const DataRow = ({ color, label, value, icon }) => (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="caption" sx={{ color: color || '#94A3B8', display: 'flex', alignItems: 'center', gap: 1, opacity: 0.9 }}>{icon ? icon : <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: color }} />}{label}</Typography>
            <Typography variant="caption" fontWeight="bold" sx={{ color: 'white' }}>{value}</Typography>
        </Box>
    );

    return (
        <Paper elevation={0} sx={{ p: 3, borderRadius: 3, border: '1px solid #E2E8F0', mb: 3, height: 550, position: 'relative' }}>
            {nextRace && (
                <Box sx={{ position: 'absolute', top: 20, right: 20, zIndex: 10, bgcolor: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(4px)', border: '1px solid #FECACA', borderRadius: 2, p: 1.5, boxShadow: '0 4px 20px rgba(239, 68, 68, 0.1)', display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Box sx={{ bgcolor: '#FEF2F2', p: 1, borderRadius: 1.5 }}><EmojiEvents sx={{ color: '#EF4444' }} /></Box>
                    <Box><Typography variant="caption" color="error" fontWeight="bold" display="block">PRÓXIMO OBJETIVO</Typography><Typography variant="subtitle2" fontWeight="800" sx={{ lineHeight: 1.2 }}>{nextRace.race.nombre}</Typography><Typography variant="caption" color="textSecondary">Faltan <strong>{weeksToRace} semanas</strong></Typography></Box>
                </Box>
            )}
            
            <Grid container spacing={2} alignItems="center" sx={{ mb: 3 }}>
                <Grid item xs={12} md={4}>
                    <FormControl fullWidth size="small">
                        <Select value={metric} onChange={(e) => setMetric(e.target.value)} sx={{ fontWeight: 700, color: '#1E293B', bgcolor: '#F8FAFC' }}>
                            {Object.keys(METRICS).map(key => (<MenuItem key={key} value={key}><Stack direction="row" gap={1} alignItems="center">{METRICS[key].icon} {METRICS[key].label}</Stack></MenuItem>))}
                        </Select>
                    </FormControl>
                    {metric === 'TIME' && (
                        <Box sx={{ mt: 1, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: COLORS.CALORIES }} />
                                <Typography variant="caption" sx={{ color: '#475569', fontWeight: 800 }}>Calorías totales</Typography>
                            </Box>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#475569' }} />
                                <Typography variant="caption" sx={{ color: '#475569', fontWeight: 800 }}>Duración</Typography>
                            </Box>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#22C55E' }} />
                                <Typography variant="caption" sx={{ color: '#475569', fontWeight: 800 }}>Esfuerzo</Typography>
                            </Box>
                        </Box>
                    )}
                </Grid>
                <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { md: 'center' } }}><ToggleButtonGroup value={sport} exclusive onChange={(e, val) => val && setSport(val)} size="small" sx={{ bgcolor: '#F8FAFC' }}><ToggleButton value="ALL" sx={{ px: 2 }}><Layers/></ToggleButton><ToggleButton value="RUN" sx={{ px: 2 }}><DirectionsRun/></ToggleButton><ToggleButton value="BIKE" sx={{ px: 2 }}><PedalBike/></ToggleButton></ToggleButtonGroup></Grid>
                <Grid item xs={12} md={4} sx={{ display: 'flex', justifyContent: { md: 'flex-end' } }}><ToggleButtonGroup value={range} exclusive onChange={(e, val) => val && setRange(val)} size="small"><ToggleButton value="3M">3M</ToggleButton><ToggleButton value="SEASON">TEMP</ToggleButton><ToggleButton value="1Y">1 AÑO</ToggleButton></ToggleButtonGroup></Grid>
            </Grid>

            {!hasWeeklyStats && (
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                    Sin datos
                </Typography>
            )}

            {/* Sin ResponsiveContainer: ancho medido por ResizeObserver */}
            <Box ref={chartWrapRef} sx={{ width: '100%', height: 400, minHeight: 400, position: 'relative' }}>
                <ComposedChart
                        key={`${String(granularity || 'DAILY')}-${metric}-${sport}-${range}`}
                        width={Math.max(320, Number(chartWidth) || 900)}
                        height={400}
                        data={isWeekly ? weeklyChartData : filteredData}
                        margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                >
                    <defs>
                        <linearGradient id="colorCtl" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={COLORS.FITNESS} stopOpacity={0.2}/><stop offset="95%" stopColor={COLORS.FITNESS} stopOpacity={0}/></linearGradient>
                        <linearGradient id="colorElev" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={COLORS.ELEV_POS} stopOpacity={0.4}/><stop offset="95%" stopColor={COLORS.ELEV_POS} stopOpacity={0.1}/></linearGradient>
                        <linearGradient id="colorNeg" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={COLORS.ELEV_NEG} stopOpacity={0.2}/><stop offset="95%" stopColor={COLORS.ELEV_NEG} stopOpacity={0.0}/></linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={COLORS.GRID} />
                    <XAxis
                        dataKey={isWeekly ? "week" : "fecha"}
                        tickFormatter={(str) => (isWeekly ? String(str || "") : safeFormat(str, 'd MMM'))}
                        tick={{ fontSize: 10, fill: '#94A3B8' }}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={40}
                    />
                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} />
                    <YAxis yAxisId="right" orientation="right" hide={!(isWeekly && metric === 'TIME')} tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} />
                    <Tooltip content={isWeekly ? <WeeklyTooltip /> : <CustomTooltip />} />
                    {metric !== 'TIME' && <Legend wrapperStyle={{ paddingTop: '10px' }} iconType="circle"/>}
                    {!isWeekly && <ReferenceArea x1={todayStr} ifOverflow="extendDomain" fill="rgba(241, 245, 249, 0.5)" />}

                    {!isWeekly && metric === 'PERFORMANCE' && (<><Bar yAxisId="left" dataKey="load" name="Carga" barSize={4} fill="#94A3B8" opacity={0.3} /><Area yAxisId="left" type="monotone" dataKey="ctl" name="Fitness" stroke={COLORS.FITNESS} strokeWidth={3} fill="url(#colorCtl)" dot={false} /><Line yAxisId="left" type="monotone" dataKey="atl" name="Fatiga" stroke={COLORS.FATIGUE} strokeWidth={2} dot={false} strokeDasharray="3 3" /><Line yAxisId="right" type="monotone" dataKey="tsb" name="Forma" stroke={COLORS.FORM} strokeWidth={2} dot={false} /></>)}
                    
                    {metric === 'DISTANCE' && (
                        isWeekly ? (
                            <Bar yAxisId="left" dataKey="km" name="Distancia (km)" barSize={10} radius={[2, 2, 0, 0]} fill={COLORS.BAR_REAL} />
                        ) : (
                            <Bar yAxisId="left" dataKey="dist" name="Distancia (km)" barSize={8} radius={[2, 2, 0, 0]}>{filteredData.map((entry, index) => (<Cell key={`cell-${index}`} fill={entry.is_future ? COLORS.BAR_PLAN : COLORS.BAR_REAL} />))}</Bar>
                        )
                    )}
                    
                    {metric === 'TIME' && (
                        isWeekly ? (
                            <Bar yAxisId="left" dataKey="calories_kcal" name="Calorías (kcal)" barSize={10} radius={[2, 2, 0, 0]} fill={COLORS.CALORIES} />
                        ) : (
                            <Bar yAxisId="left" dataKey="calories" name="Calorías (kcal)" barSize={8} radius={[2, 2, 0, 0]} fill={COLORS.CALORIES} />
                        )
                    )}

                    {metric === 'ELEVATION' && (
                        isWeekly ? (
                            <Bar yAxisId="left" dataKey="elev_gain_m" name="Desnivel Positivo (m)" barSize={10} radius={[2, 2, 0, 0]} fill={COLORS.ELEV_POS} />
                        ) : (
                            <>
                              <Area yAxisId="left" type="monotone" dataKey="elev_gain" name="Desnivel Positivo (m)" stroke={COLORS.ELEV_POS} fill="url(#colorElev)" />
                              <Area yAxisId="left" type="monotone" dataKey="elev_loss_plot" name="Desnivel -" stroke={COLORS.ELEV_NEG} fill="url(#colorNeg)" />
                            </>
                        )
                    )}

                    {!isWeekly && <ReferenceLine yAxisId="left" x={todayStr} stroke={COLORS.TODAY_LINE} strokeDasharray="3 3" />}
                    {!isWeekly && races.map((race, idx) => (<ReferenceLine yAxisId="left" key={idx} x={race.fecha} stroke="#EF4444" strokeWidth={2} strokeDasharray="3 3" label={{ position: 'top', value: '🏁', fontSize: 20 }} />))}
                    
                    {!isWeekly && filteredData.length > 0 && (
                         <Brush dataKey="fecha" height={20} stroke={COLORS.GRID} startIndex={startIndex} tickFormatter={(str) => safeFormat(str, 'MMM')}/>
                    )}
                </ComposedChart>
            </Box>

            {/* Leyendas movidas arriba (junto al selector de métricas) */}
        </Paper>
    );
};

export default StudentPerformanceChart;