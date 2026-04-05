import React, { useEffect, useState } from 'react';
import { Box, Typography, Button, IconButton } from '@mui/material';
import { Close } from '@mui/icons-material';

const LS_PROMPT_DISMISSED = 'quantoryn_pwa_dismissed_until';
const LS_ACTION_COMPLETED = 'quantoryn_action_completed';
const DISMISS_DAYS = 7;

/**
 * PWAInstallPrompt — shows a "Install Quantoryn" banner after the user has
 * completed one action (flag set via localStorage 'quantoryn_action_completed').
 * Only visible on mobile (xs). Dismissed for 7 days on "Ahora no".
 */
export default function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);

      // Only show if user has completed at least one action
      const actionDone = localStorage.getItem(LS_ACTION_COMPLETED) === 'true';
      if (!actionDone) return;

      // Check if dismissed recently
      const dismissedUntil = localStorage.getItem(LS_PROMPT_DISMISSED);
      if (dismissedUntil && Date.now() < Number(dismissedUntil)) return;

      setVisible(true);
    };

    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  // Also check once the action flag is set (e.g., after a save elsewhere in the app)
  useEffect(() => {
    if (!deferredPrompt) return;

    const check = () => {
      const actionDone = localStorage.getItem(LS_ACTION_COMPLETED) === 'true';
      const dismissedUntil = localStorage.getItem(LS_PROMPT_DISMISSED);
      const dismissed = dismissedUntil && Date.now() < Number(dismissedUntil);
      if (actionDone && !dismissed) setVisible(true);
    };

    window.addEventListener('storage', check);
    return () => window.removeEventListener('storage', check);
  }, [deferredPrompt]);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setVisible(false);
      setDeferredPrompt(null);
    }
  };

  const handleDismiss = () => {
    const until = Date.now() + DISMISS_DAYS * 24 * 60 * 60 * 1000;
    localStorage.setItem(LS_PROMPT_DISMISSED, String(until));
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <Box
      sx={{
        position: 'fixed',
        top: 48, // below compact mobile header
        left: 0,
        right: 0,
        zIndex: 1400,
        display: { xs: 'flex', sm: 'none' },
        alignItems: 'center',
        gap: 1.5,
        px: 2,
        py: 1.25,
        bgcolor: '#0D1117',
        borderBottom: '1px solid rgba(0, 212, 170,0.3)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      }}
    >
      <Typography sx={{ fontSize: '0.8rem', color: 'white', flex: 1, lineHeight: 1.4 }}>
        Instalá Quantoryn para acceso rápido
      </Typography>
      <Button
        size="small"
        onClick={handleInstall}
        sx={{
          bgcolor: '#00D4AA',
          color: 'white',
          fontSize: '0.75rem',
          fontWeight: 700,
          px: 1.5,
          py: 0.5,
          borderRadius: 1.5,
          minWidth: 0,
          '&:hover': { bgcolor: '#e06900' },
          flexShrink: 0,
        }}
      >
        Instalar
      </Button>
      <IconButton size="small" onClick={handleDismiss} sx={{ color: '#94a3b8', p: 0.5 }}>
        <Close sx={{ fontSize: 16 }} />
      </IconButton>
    </Box>
  );
}
