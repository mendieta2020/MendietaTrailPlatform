import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { 
  BarChart, Area, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
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
import { format, parseISO, addMonths, subMonths, isValid, differenceInWeeks } from 'date-fns';
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

// Helper seguro para fechas
const safeFormat = (dateStr, formatStr) => {
    try {
        if (!dateStr) return '';
        const date = parseISO(dateStr);
        return isValid(date) ? format(date, formatStr, { locale: es }) : '';
    } catch { return ''; }
};

const StudentPerformanceChart = ({ alumnoId, weeklyStats, granularity } = {}) => {
    const [data, setData] = useState([]);
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

    // En semanal, no arrancamos en PERFORMANCE (no aplica) para evitar panel "vacío"
    useEffect(() => {
        if (isWeekly && metric === 'PERFORMANCE') setMetric('DISTANCE');
    }, [isWeekly, metric]);

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
                        setData(sanitizedData);
                    } else { setData([]); }
                }
            } catch (err) {
                console.error("Error PMC:", err);
                if (isMounted) setData([]);
            } finally {
                if (isMounted) setLoading(false);
            }
        };
        fetchData();
        return () => { isMounted = false; };
    }, [sport, alumnoId]);

    // Filtrado de Datos
    const getFilteredData = () => {
        if (!data.length) return [];
        const today = new Date();
        let startDate, endDate;

        switch (range) {
            case '3M': startDate = subMonths(today, 3); endDate = addMonths(today, 1); break;
            case 'SEASON': startDate = subMonths(today, 6); endDate = addMonths(today, 6); break;
            case '1Y': startDate = subMonths(today, 12); endDate = addMonths(today, 6); break;
            default: startDate = subMonths(today, 6); endDate = addMonths(today, 6);
        }
        
        return data.filter(d => {
            const dDate = parseISO(d.fecha);
            return isValid(dDate) && dDate >= startDate && dDate <= endDate;
        });
    };

    const filteredData = getFilteredData();

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
    const weeklyChartData = isWeekly
        ? filteredWeeklyData.map((w) => {
            const startStr = w.range_start;
            const endStr = w.range_end;
            let timeMin = Number(w.time_min) || 0;
            if (timeMin === 0 && startStr && endStr && filteredData.length) {
                try {
                    const start = parseISO(startStr);
                    const end = parseISO(endStr);
                    if (isValid(start) && isValid(end)) {
                        let sum = 0;
                        for (const d of filteredData) {
                            try {
                                const dd = parseISO(d.fecha);
                                if (isValid(dd) && dd >= start && dd <= end && !d.is_future) {
                                    sum += Number(d.time) || 0; // minutos
                                }
                            } catch {
                                // ignore
                            }
                        }
                        timeMin = Math.round(sum);
                    }
                } catch {
                    // ignore
                }
            }
            return {
                ...w,
                // Aseguramos keys correctas (no NaN)
                calories_kcal: Math.round(Number(w.calories_kcal) || 0),
                time_min: Math.round(Number(timeMin) || 0),
            };
        })
        : [];
    
    // Próximo objetivo
    let nextRace = null, weeksToRace = null;
    if (races.length > 0) {
        nextRace = races.find(r => r.fecha >= todayStr);
        if (nextRace) weeksToRace = differenceInWeeks(parseISO(nextRace.fecha), new Date());
    }

    // Calculamos índice de inicio para Brush
    const startIndex = filteredData.length > 60 ? filteredData.length - 60 : 0;

    if (loading) return <Paper elevation={0} sx={{ p: 4, display:'flex', justifyContent:'center', borderRadius: 3, height: 500, border: '1px solid #E2E8F0' }}><CircularProgress /></Paper>;

    // Si el atleta aún no inyectó weeklyStats pero ya estamos en semanal, mostramos loading suave.
    // Evita "pantalla vacía" durante el primer render.
    if (isWeekly && !hasWeeklyStats) {
        return (
            <Paper elevation={0} sx={{ p: 4, borderRadius: 3, height: 500, border: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'center', gap: 2 }}>
                <CircularProgress />
                <Typography color="textSecondary" fontWeight="bold">Cargando datos de rendimiento...</Typography>
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

    // Estado vacío seguro
    if ((!isWeekly && !data.length) || (isWeekly && !filteredWeeklyData.length)) return (
        <Paper elevation={0} sx={{ p: 4, textAlign:'center', borderRadius: 3, height: 500, border: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display:'flex', flexDirection:'column', justifyContent:'center', alignItems:'center' }}>
            <AutoGraph sx={{ fontSize: 60, color: '#CBD5E1', mb: 2 }} />
            <Typography color="textSecondary" fontWeight="bold">Sin datos</Typography>
        </Paper>
    );

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length && label) {
            const dayData = data.find(d => d.fecha === label);
            if (!dayData) return null;
            const isFut = dayData.is_future;
            
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
                        ) : (<DataRow color="#fff" label="Valor Principal" value={payload[0].value} />)}
                        <Divider sx={{ my: 1, borderColor: 'rgba(255,255,255,0.1)' }} />
                        {metric === 'TIME' && dayData.calories != null && (
                          <DataRow
                            icon={<LocalFireDepartment fontSize="inherit"/>}
                            label="Calorías"
                            value={`${dayData.calories} kcal`}
                            color={COLORS.CALORIES}
                          />
                        )}
                        {metric === 'TIME' && dayData.effort != null && (
                          <DataRow
                            icon={<Layers fontSize="inherit" />}
                            label="Esfuerzo"
                            value={dayData.effort}
                            color="#22C55E"
                          />
                        )}
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
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.75)' }}>
                                Duración Total
                            </Typography>
                            <Typography variant="caption" fontWeight="bold" sx={{ color: 'white' }}>
                                {tmin} min
                            </Typography>
                        </Box>
                    )}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="caption" sx={{ color: COLORS.CALORIES, opacity: 0.95 }}>
                            Calorías Totales
                        </Typography>
                        <Typography variant="caption" fontWeight="bold" sx={{ color: 'white' }}>
                            {kcal} kcal
                        </Typography>
                    </Box>
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
                <BarChart
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
                    <Legend wrapperStyle={{ paddingTop: '10px' }} iconType="circle"/>
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
                            <>
                                <Bar yAxisId="left" dataKey="time_min" name="Duración (min)" barSize={10} radius={[2, 2, 0, 0]} fill="#475569" />
                                <Bar yAxisId="right" dataKey="calories_kcal" name="Calorías (kcal)" barSize={10} radius={[2, 2, 0, 0]} fill={COLORS.CALORIES} />
                            </>
                        ) : (
                            <><Bar yAxisId="left" dataKey="time" name="Tiempo (min)" barSize={8} radius={[2, 2, 0, 0]}>{filteredData.map((entry, index) => (<Cell key={`cell-${index}`} fill={entry.is_future ? COLORS.TIME_PLAN : COLORS.TIME_REAL} />))}</Bar><Line yAxisId="right" type="monotone" dataKey="calories" name="Kcal" stroke={COLORS.CALORIES} strokeWidth={2} dot={false} /></>
                        )
                    )}

                    {metric === 'ELEVATION' && (
                        isWeekly ? (
                            <Bar yAxisId="left" dataKey="elev_gain_m" name="Desnivel +" barSize={10} radius={[2, 2, 0, 0]} fill={COLORS.ELEV_POS} />
                        ) : (
                            <><Area yAxisId="left" type="monotone" dataKey="elev_gain" name="Desnivel +" stroke={COLORS.ELEV_POS} fill="url(#colorElev)" /><Area yAxisId="left" type="monotone" dataKey="elev_loss_plot" name="Desnivel -" stroke={COLORS.ELEV_NEG} fill="url(#colorNeg)" /></>
                        )
                    )}

                    {!isWeekly && <ReferenceLine yAxisId="left" x={todayStr} stroke={COLORS.TODAY_LINE} strokeDasharray="3 3" />}
                    {!isWeekly && races.map((race, idx) => (<ReferenceLine yAxisId="left" key={idx} x={race.fecha} stroke="#EF4444" strokeWidth={2} strokeDasharray="3 3" label={{ position: 'top', value: '🏁', fontSize: 20 }} />))}
                    
                    {!isWeekly && filteredData.length > 0 && (
                         <Brush dataKey="fecha" height={20} stroke={COLORS.GRID} startIndex={startIndex} tickFormatter={(str) => safeFormat(str, 'MMM')}/>
                    )}
                </BarChart>
            </Box>
        </Paper>
    );
};

export default StudentPerformanceChart;