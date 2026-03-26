import { useEffect, useRef } from 'react';
import { Box, Divider, Tooltip } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';

const ITEM_SX = {
  display: 'flex',
  alignItems: 'center',
  gap: 1.2,
  px: 2,
  py: 0.9,
  cursor: 'pointer',
  fontSize: '0.83rem',
  color: '#e2e8f0',
  borderRadius: 1,
  mx: 0.5,
  '&:hover': { bgcolor: 'rgba(255,255,255,0.07)' },
};

const DANGER_SX = {
  ...ITEM_SX,
  color: '#f87171',
  '&:hover': { bgcolor: 'rgba(239,68,68,0.1)' },
};

const DISABLED_SX = {
  ...ITEM_SX,
  color: '#4a5568',
  cursor: 'not-allowed',
  '&:hover': {},
};

const COMPLETED_STATUSES = new Set(['completed']);

export default function CalendarContextMenu({
  x, y, event, onClose,
  onEdit, onDuplicate, onDelete, onCopyWeek, onDeleteWeek,
}) {
  const ref = useRef(null);

  const isCompleted = COMPLETED_STATUSES.has(event?.resource?.status);

  useEffect(() => {
    const handle = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handle);
    document.addEventListener('contextmenu', handle);
    return () => {
      document.removeEventListener('mousedown', handle);
      document.removeEventListener('contextmenu', handle);
    };
  }, [onClose]);

  return (
    <Box
      ref={ref}
      sx={{
        position: 'fixed',
        top: y,
        left: x,
        zIndex: 3000,
        bgcolor: '#1e293b',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 2,
        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        minWidth: 190,
        py: 0.75,
      }}
    >
      <Box sx={ITEM_SX} onClick={() => { onEdit(event); onClose(); }}>
        <EditIcon sx={{ fontSize: 16, opacity: 0.7 }} />
        Editar sesión
      </Box>
      <Box sx={ITEM_SX} onClick={() => { onDuplicate(event); onClose(); }}>
        <ContentCopyIcon sx={{ fontSize: 16, opacity: 0.7 }} />
        Duplicar...
      </Box>

      {isCompleted ? (
        <Tooltip title="Las sesiones completadas no se pueden eliminar" placement="right">
          <Box sx={DISABLED_SX}>
            <DeleteIcon sx={{ fontSize: 16, opacity: 0.4 }} />
            Eliminar sesión
          </Box>
        </Tooltip>
      ) : (
        <Box sx={DANGER_SX} onClick={() => { onDelete(event); onClose(); }}>
          <DeleteIcon sx={{ fontSize: 16, opacity: 0.7 }} />
          Eliminar sesión
        </Box>
      )}

      <Divider sx={{ my: 0.5, borderColor: 'rgba(255,255,255,0.07)' }} />
      <Box sx={ITEM_SX} onClick={() => { onCopyWeek(event); onClose(); }}>
        <CalendarMonthIcon sx={{ fontSize: 16, opacity: 0.7 }} />
        Copiar semana
      </Box>
      <Box sx={DANGER_SX} onClick={() => { onDeleteWeek(event); onClose(); }}>
        <DeleteSweepIcon sx={{ fontSize: 16, opacity: 0.7 }} />
        Eliminar semana
      </Box>
    </Box>
  );
}
