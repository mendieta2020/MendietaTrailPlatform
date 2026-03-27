/**
 * MessagesDrawer.jsx — PR-147 (updated)
 *
 * Right-side drawer for the athlete showing coach messages.
 * - Unread messages show amber background + orange dot
 * - Athletes can reply to their coach directly from the drawer
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
} from '@mui/material';
import { Close as CloseIcon, Send as SendIcon } from '@mui/icons-material';
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

const MessagesDrawer = ({ open, onClose, messages, orgId, onMessageSent }) => {
  const displayed = messages.slice(0, 20);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');

  // Find the coach to reply to: sender of the most recent message
  const coachSenderId = displayed.length > 0 ? displayed[0].sender_id : null;

  const handleReply = async () => {
    if (!replyText.trim() || !coachSenderId || !orgId) return;
    setSending(true);
    setReplyError('');
    try {
      await sendMessage(orgId, {
        recipient_id: coachSenderId,
        content: replyText.trim(),
        alert_type: 'athlete_reply',
        whatsapp_sent: false,
      });
      setReplyText('');
      onMessageSent?.();
    } catch (err) {
      const detail = err?.response?.data?.detail
        || err?.response?.data?.recipient_id
        || 'Error al enviar. Intentá de nuevo.';
      setReplyError(Array.isArray(detail) ? detail[0] : detail);
    } finally {
      setSending(false);
    }
  };

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
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Message list — scrollable */}
      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {displayed.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              No tenés mensajes todavía.
            </Typography>
          </Box>
        ) : (
          <List disablePadding>
            {displayed.map((msg, idx) => {
              const isUnread = !msg.read_at;
              const isFromAthlete = msg.sender_id !== coachSenderId;
              return (
                <React.Fragment key={msg.id}>
                  <ListItem
                    alignItems="flex-start"
                    sx={{
                      px: 2,
                      py: 1.5,
                      bgcolor: isFromAthlete
                        ? '#F0FDF4'          // athlete reply = green tint
                        : isUnread
                          ? '#FFFBEB'        // unread coach = amber
                          : 'white',
                      gap: 1,
                    }}
                  >
                    {/* Unread dot */}
                    <Box sx={{ pt: '6px', minWidth: 10 }}>
                      {isUnread && !isFromAthlete && (
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: '#F97316',
                          }}
                        />
                      )}
                    </Box>
                    <Box sx={{ flexGrow: 1 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, color: isFromAthlete ? '#16A34A' : '#374151' }}>
                          {isFromAthlete ? 'Tú' : msg.sender_name}
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
                          display: '-webkit-box',
                          WebkitLineClamp: 4,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
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

      {/* Reply box — pinned at bottom */}
      {coachSenderId && (
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
              placeholder="Responderle a tu coach..."
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleReply();
                }
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  fontSize: '0.82rem',
                  borderRadius: 2,
                },
              }}
            />
            <IconButton
              onClick={handleReply}
              disabled={sending || !replyText.trim()}
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
