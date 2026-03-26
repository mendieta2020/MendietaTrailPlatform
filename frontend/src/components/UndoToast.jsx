import { useEffect, useRef, useState } from 'react';
import { Box, Typography, LinearProgress } from '@mui/material';

export default function UndoToast({ message, onUndo, onClose, duration = 5000 }) {
  const [progress, setProgress] = useState(100);
  const startRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    startRef.current = Date.now();
    const tick = () => {
      const elapsed = Date.now() - startRef.current;
      const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(remaining);
      if (remaining > 0) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        onClose();
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [duration, onClose]);

  return (
    <Box
      sx={{
        position: 'fixed',
        bottom: 24,
        left: 24,
        zIndex: 2000,
        minWidth: 280,
        maxWidth: 380,
        bgcolor: '#1e293b',
        borderRadius: 2,
        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, gap: 1.5 }}>
        <Typography variant="body2" sx={{ flex: 1, color: '#e2e8f0' }}>
          {message}
        </Typography>
        <Box
          component="button"
          onClick={() => { onUndo(); onClose(); }}
          sx={{
            background: 'none',
            border: '1px solid rgba(245,124,0,0.5)',
            borderRadius: 1,
            color: '#F57C00',
            cursor: 'pointer',
            fontWeight: 700,
            fontSize: '0.78rem',
            px: 1.2,
            py: 0.4,
            whiteSpace: 'nowrap',
            '&:hover': { bgcolor: 'rgba(245,124,0,0.1)' },
          }}
        >
          Deshacer
        </Box>
      </Box>
      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{
          height: 3,
          bgcolor: 'rgba(255,255,255,0.08)',
          '& .MuiLinearProgress-bar': { bgcolor: '#F57C00', transition: 'none' },
        }}
      />
    </Box>
  );
}
