import React from 'react';
import { Paper, Typography, Box } from '@mui/material';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell 
} from 'recharts';

const data = [
  { name: 'Lun', valor: 80 },
  { name: 'Mar', valor: 65 },
  { name: 'Mie', valor: 90 },
  { name: 'Jue', valor: 45 },
  { name: 'Vie', valor: 70 },
  { name: 'Sab', valor: 100 },
  { name: 'Dom', valor: 30 },
];

const ComplianceChart = () => {
  return (
    <Paper sx={{ p: 3, height: '100%', borderRadius: 3 }}>
      <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
        Cumplimiento Semanal 🏃‍♂️
      </Typography>
      <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
        % de sesiones completadas por el equipo
      </Typography>
      
      <Box sx={{ height: 250, width: '100%' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" axisLine={false} tickLine={false} />
            <Tooltip 
              cursor={{ fill: '#f5f5f5' }}
              contentStyle={{ borderRadius: '10px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
            />
            <Bar dataKey="valor" radius={[5, 5, 0, 0]} barSize={30}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.valor > 75 ? '#2e7d32' : entry.valor > 40 ? '#F57C00' : '#d32f2f'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </Paper>
  );
};

export default ComplianceChart;