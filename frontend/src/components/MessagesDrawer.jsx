/**
 * MessagesDrawer.jsx — PR-147 (final)
 *
 * Right-side drawer for the athlete:
 * - Full conversation thread (sent + received)
 * - "Tú" = messages sent by the current user (currentUserId)
 * - Reply to a coach message OR start a new conversation
 * - Reply box pinned at bottom
 */

import React, { useState } from 'react';
import {
  Box,
  Drawer,
  Typography,
  Divider,
  IconButton,
  List,
  ListItem,
  TextField,
  Button,
  CircularProgress,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
} from '@mui/material';
import { Close as CloseIcon, Send as SendIcon, Edit as EditIcon } from '@mui/icons-material';
import { sendMessage } from '../api/messages';

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days} día${days !== 1 ? 's' : ''}`;
}

const MessagesDrawer = ({ open, onClose, messages, coaches = [], orgId, currentUserId, onMessageSent }) => {
  const displayed = messages.slice(0, 30);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const [composing, setComposing] = useState(false);
  const [selectedCoachId, setSelectedCoachId] = useState('');

  // Find the default recipient: sender of the most recent message NOT from current user
  const lastIncoming = displayed.find((m) => m.sender_id !== currentUserId);
  const defaultRecipientId = lastIncoming?.sender_id ?? null;

  // Who to send to: if composing from scratch, use selectedCoachId; otherwise reply to last sender
  const recipientId = composing ? selectedCoachId : defaultRecipientId;

  const handleSend = async () => {
    if (!replyText.trim() || !recipientId || !orgId) return;
    setSending(true);
    setReplyError('');
    try {
      await sendMessage(orgId, {
        recipient_id: recipientId,
        content: replyText.trim(),
        alert_type: 'athlete_reply',
        whatsapp_sent: false,
      });
      setReplyText('');
      setComposing(false);
      setSelectedCoachId('');
      onMessageSent?.();
    } catch (err) {
      const data = err?.response?.data;
      const detail = data?.detail || data?.recipient_id || 'Error al enviar. Intentá de nuevo.';
      setReplyError(Array.isArray(detail) ? detail[0] : detail);
    } finally {
      setSending(false);
    }
  };

  const canSend = !!(recipientId && replyText.trim() && orgId);
  const hasCoaches = coaches.length > 0;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 360, bgcolor: '#F8FAFC', display: 'flex', flexDirection: 'column' } }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1, color: '#1E293B' }}>
          Mensajes de tu coach
        </Typography>
        {hasCoaches && (
          <IconButton
            size="small"
            title="Nuevo mensaje"
            onClick={() => setComposing((v) => !v)}
            sx={{ color: composing ? '#F57C00' : '#64748B', mr: 0.5 }}
          >
            <EditIcon fontSize="small" />
          </IconButton>
        )}
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Compose new message panel */}
      {composing && hasCoaches && (
        <Box sx={{ px: 2, py: 1.5, bgcolor: '#FFF7ED', borderBottom: '1px solid #FED7AA', flexShrink: 0 }}>
          <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600, display: 'block', mb: 1 }}>
            Nuevo mensaje
          </Typography>
          <FormControl fullWidth size="small">
            <InputLabel sx={{ fontSize: '0.82rem' }}>Enviar a</InputLabel>
            <Select
              value={selectedCoachId}
              label="Enviar a"
              onChange={(e) => setSelectedCoachId(e.target.value)}
              sx={{ fontSize: '0.82rem' }}
            >
              {coaches.map((c) => (
                <MenuItem key={c.user_id} value={c.user_id} sx={{ fontSize: '0.82rem' }}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      {/* Message list — scrollable */}
      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {displayed.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              No tenés mensajes todavía.
            </Typography>
            {hasCoaches && (
              <Button
                size="small"
                variant="outlined"
                sx={{ mt: 2, fontSize: '0.78rem', borderColor: '#F57C00', color: '#F57C00' }}
                onClick={() => setComposing(true)}
                startIcon={<EditIcon fontSize="small" />}
              >
                Escribirle al coach
              </Button>
            )}
          </Box>
        ) : (
          <List disablePadding>
            {displayed.map((msg, idx) => {
              const isFromMe = currentUserId && msg.sender_id === currentUserId;
              const isUnread = !msg.read_at && !isFromMe;
              return (
                <React.Fragment key={msg.id}>
                  <ListItem
                    alignItems="flex-start"
                    sx={{
                      px: 2,
                      py: 1.5,
                      bgcolor: isFromMe
                        ? '#F0FDF4'       // athlete's own message = green tint
                        : isUnread
                          ? '#FFFBEB'     // unread coach message = amber
                          : 'white',
                      gap: 1,
                      justifyContent: isFromMe ? 'flex-end' : 'flex-start',
                    }}
                  >
                    {/* Unread dot — only for incoming unread */}
                    {!isFromMe && (
                      <Box sx={{ pt: '6px', minWidth: 10 }}>
                        {isUnread && (
                          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#F97316' }} />
                        )}
                      </Box>
                    )}
                    <Box sx={{ maxWidth: '85%' }}>
                      <Box sx={{ display: 'flex', justifyContent: isFromMe ? 'flex-end' : 'space-between', mb: 0.25, gap: 2 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, color: isFromMe ? '#16A34A' : '#374151' }}>
                          {isFromMe ? 'Tú' : msg.sender_name}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#9CA3AF' }}>
                          {timeAgo(msg.created_at)}
                        </Typography>
                      </Box>
                      <Typography
                        variant="body2"
                        sx={{
                          color: '#4B5563',
                          fontSize: '0.82rem',
                          lineHeight: 1.4,
                        }}
                      >
                        {msg.content}
                      </Typography>
                    </Box>
                  </ListItem>
                  {idx < displayed.length - 1 && (
                    <Divider sx={{ borderColor: '#F1F5F9' }} />
                  )}
                </React.Fragment>
              );
            })}
          </List>
        )}
      </Box>

      {/* Reply / compose box — pinned at bottom */}
      {(defaultRecipientId || (composing && selectedCoachId)) && (
        <Box sx={{ px: 2, py: 1.5, bgcolor: 'white', borderTop: '1px solid #E2E8F0', flexShrink: 0 }}>
          {replyError && (
            <Typography variant="caption" color="error" sx={{ display: 'block', mb: 0.5 }}>
              {replyError}
            </Typography>
          )}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
            <TextField
              fullWidth
              multiline
              maxRows={3}
              size="small"
              placeholder={composing ? 'Escribí tu mensaje...' : 'Responderle a tu coach...'}
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              sx={{ '& .MuiOutlinedInput-root': { fontSize: '0.82rem', borderRadius: 2 } }}
            />
            <IconButton
              onClick={handleSend}
              disabled={sending || !canSend}
              size="small"
              sx={{
                bgcolor: '#F57C00',
                color: 'white',
                '&:hover': { bgcolor: '#E65100' },
                '&.Mui-disabled': { bgcolor: '#E5E7EB', color: '#9CA3AF' },
                width: 36,
                height: 36,
                flexShrink: 0,
              }}
            >
              {sending ? <CircularProgress size={16} color="inherit" /> : <SendIcon fontSize="small" />}
            </IconButton>
          </Box>
        </Box>
      )}
    </Drawer>
  );
};

export default MessagesDrawer;
