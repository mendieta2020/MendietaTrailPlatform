import React, { useState, useEffect } from 'react';
import { Grid, Paper, Typography, Box, CircularProgress, Alert, Divider, MenuItem, Select, FormControl, InputLabel } from '@mui/material';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, Line
} from 'recharts';
import { 
  PeopleAlt, AttachMoney, MonitorHeart, LocalHospital, 
  TrendingUp, CalendarMonth
} from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';
import PaymentsWidget from '../components/widgets/PaymentsWidget';
import ComplianceChart from '../components/widgets/ComplianceChart';
import { format, subMonths, startOfYear, endOfYear, startOfMonth, endOfMonth, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

// --- COMPONENTE DE TARJETA KPI ---
const StatCard = ({ title, value, sub, color, icon: Icon, loading }) => (
  <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderLeft: `4px solid ${color}`, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, letterSpacing: 0.5 }}>{title.toUpperCase()}</Typography>
      {Icon && <Icon sx={{ color: color, opacity: 0.7 }} />}
    </Box>
    
    <Box sx={{ mt: 2, position: 'relative' }}>
        {loading ? <CircularProgress size={20} sx={{ color: color }} /> : (
            <Typography variant="h4" sx={{ fontWeight: 700, color: '#1E293B' }}>{value}</Typography>
        )}
        <Typography variant="body2" sx={{ color: color, fontWeight: 500, mt: 0.5, fontSize: '0.875rem' }}>
            {sub}
        </Typography>
    </Box>
  </Paper>
);

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Estado del Filtro de Tiempo
  const [periodo, setPeriodo] = useState('THIS_MONTH');
  
  // Datos
  const [kpiData, setKpiData] = useState({ alumnos: 0, ingresos: 0 });
  const [pmcData, setPmcData] = useState([]); // Datos reales del Backend
  const [pagosData, setPagosData] = useState([]);

  // --- EFECTO DE CARGA DE DATOS ---
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        
        // 1. Cargar KPIs Básicos
        const [resAlumnos, resPagos] = await Promise.all([
          client.get('/api/alumnos/'),
          client.get('/api/pagos/')
        ]);

        const totalIngresos = resPagos.data.reduce((acc, pago) => acc + parseFloat(pago.monto), 0);
        setKpiData({ 
            alumnos: resAlumnos.data.length, 
            ingresos: totalIngresos 
        });
        setPagosData(resPagos.data);

        // 2. Cargar Datos Científicos (PMC) - Opcional: Pasar fechas en query params
        // Por ahora traemos todo y filtramos en frontend (para MVP es rápido)
        // En producción, filtraremos en backend: `/api/analytics/pmc/?start=...&end=...`
        const resPMC = await client.get('/api/analytics/pmc/');
        setPmcData(resPMC.data);

      } catch (err) {
        console.error("Error Dashboard:", err);
        setError("Error de conexión. Verifica tu internet.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [periodo]); // Recargar si cambia el periodo (futuro: conectar filtro al backend)

  // --- FILTRADO DE DATOS PMC SEGÚN PERIODO ---
  const getFilteredPMC = () => {
      if (!pmcData) return [];
      const now = new Date();
      let startDate = startOfMonth(now);

      if (periodo === 'LAST_3_MONTHS') startDate = subMonths(now, 3);
      if (periodo === 'THIS_YEAR') startDate = startOfYear(now);

      return pmcData.filter(d => parseISO(d.fecha) >= startDate);
  };

  const filteredPMC = getFilteredPMC();

  return (
    <Layout>
      {/* HEADER CON FILTROS */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
        <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Panel de Control</Typography>
            <Typography variant="body2" sx={{ color: '#64748B' }}>Visión general de tu negocio y atletas.</Typography>
        </Box>
        
        {/* SELECTOR DE PERIODO */}
        <FormControl size="small" sx={{ minWidth: 150, bgcolor: 'white' }}>
            <InputLabel>Período</InputLabel>
            <Select
                value={periodo}
                label="Período"
                onChange={(e) => setPeriodo(e.target.value)}
            >
                <MenuItem value="THIS_MONTH">Este Mes</MenuItem>
                <MenuItem value="LAST_3_MONTHS">Últimos 3 Meses</MenuItem>
                <MenuItem value="THIS_YEAR">Este Año</MenuItem>
            </Select>
        </FormControl>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {/* KPI CARDS */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard 
            title="Alumnos Activos" 
            value={kpiData.alumnos} 
            sub="+1 esta semana" 
            color="#0EA5E9" 
            icon={PeopleAlt}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard 
            title="Ingresos (Total)" 
            value={`$${kpiData.ingresos.toLocaleString()}`} 
            sub="Objetivo: $1M" 
            color="#10B981" 
            icon={AttachMoney}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard 
            title="Fitness Promedio" 
            value="68 CTL" 
            sub="Tendencia Positiva" 
            color="#F59E0B" 
            icon={TrendingUp}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard 
            title="Riesgo Lesión" 
            value="0" 
            sub="Sin alertas críticas" 
            color="#EF4444" 
            icon={LocalHospital}
          />
        </Grid>
      </Grid>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* GRÁFICO PMC (SCIENTIFIC DATA) */}
        <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3, borderRadius: 2, boxShadow: '0 2px 10px rgba(0,0,0,0.03)', height: 400 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, justifyContent: 'space-between' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <MonitorHeart sx={{ color: '#64748B', mr: 1 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>Rendimiento Fisiológico (PMC)</Typography>
                    </Box>
                    <Typography variant="caption" sx={{ bgcolor: '#F1F5F9', px: 1, py: 0.5, borderRadius: 1 }}>Modelo Banister Híbrido</Typography>
                </Box>
                <Divider sx={{ mb: 2 }} />
                
                <ResponsiveContainer width="100%" height="85%">
                    <AreaChart data={filteredPMC}>
                        <defs>
                            <linearGradient id="colorFit" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#0EA5E9" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#0EA5E9" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                        <XAxis 
                            dataKey="fecha" 
                            tickFormatter={(str) => format(parseISO(str), 'd MMM', { locale: es })}
                            axisLine={false} tickLine={false} tick={{fill: '#64748B', fontSize: 12}} 
                            minTickGap={30}
                        />
                        <YAxis axisLine={false} tickLine={false} tick={{fill: '#64748B', fontSize: 12}} />
                        <Tooltip 
                            contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                            labelFormatter={(str) => format(parseISO(str), 'PPPP', { locale: es })}
                        />
                        <Legend verticalAlign="top" height={36}/>
                        
                        {/* FITNESS (AREA AZUL) */}
                        <Area type="monotone" dataKey="ctl" stroke="#0EA5E9" strokeWidth={3} fillOpacity={1} fill="url(#colorFit)" name="Fitness (CTL)" />
                        
                        {/* FATIGA (LINEA ROSA) */}
                        <Line type="monotone" dataKey="atl" stroke="#EC4899" strokeWidth={2} dot={false} name="Fatiga (ATL)" />
                    </AreaChart>
                </ResponsiveContainer>
            </Paper>
        </Grid>

        {/* WIDGET PAGOS */}
        <Grid item xs={12} md={4}>
            <PaymentsWidget pagos={pagosData} />
        </Grid>
      </Grid>

      {/* GRÁFICO COMPARATIVO PLAN VS REAL (NUEVO) */}
      <Paper sx={{ p: 3, borderRadius: 2, mb: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>Volumen: Planificado vs Real</Typography>
          <Box sx={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={filteredPMC}> {/* Usamos los mismos datos PMC que ya tienen carga */}
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="fecha" tickFormatter={(str) => format(parseISO(str), 'd/M')} />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="load" name="Carga Real" fill="#10B981" radius={[4, 4, 0, 0]} />
                      {/* En el futuro agregaremos 'planned_load' aquí */}
                  </BarChart>
              </ResponsiveContainer>
          </Box>
      </Paper>

    </Layout>
  );
};

export default Dashboard;