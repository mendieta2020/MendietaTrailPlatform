/**
 * MessagesDrawer.jsx — PR-147 (final-v2)
 *
 * Right-side drawer for athletes AND coaches:
 * - Full conversation thread (sent + received)
 * - "Tú" = messages sent by the current user (currentUserId)
 * - Filter tabs: Todos / No Leídas / Leídas
 * - Reply to a specific message (per-message highlight, NOT per-sender)
 * - Compose new conversation: pencil icon → dropdown of contacts
 * - Reply box pinned at bottom
 *
 * Props:
 *   open           — boolean
 *   onClose        — fn
 *   messages       — array of message objects
 *   contacts       — array of { user_id, name } — coaches (for athletes) or athletes (for coaches)
 *   orgId          — string/number
 *   currentUserId  — number
 *   onMessageSent  — fn called after a successful send
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
  Tab,
  Tabs,
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

const MessagesDrawer = ({
  open,
  onClose,
  messages,
  contacts = [],       // unified prop: coaches list (for athletes) OR athletes list (for coaches)
  coaches,             // legacy alias — accepted for backward compat, maps to contacts
  orgId,
  currentUserId,
  onMessageSent,
}) => {
  // Backward-compat: if old `coaches` prop is passed instead of `contacts`, use it
  const contactList = contacts.length > 0 ? contacts : (coaches ?? []);

  // ── Filter tab state ────────────────────────────────────────────────────────
  const [filterTab, setFilterTab] = useState('all'); // 'all' | 'unread' | 'read'

  // ── Reply / compose state ───────────────────────────────────────────────────
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const [composing, setComposing] = useState(false);
  const [selectedContactId, setSelectedContactId] = useState('');

  // Quick-reply: tracks the SPECIFIC message the user clicked (not just sender)
  const [quickReplyMessageId, setQuickReplyMessageId] = useState(null);
  const [quickReplyRecipientId, setQuickReplyRecipientId] = useState(null);
  const [quickReplyName, setQuickReplyName] = useState('');

  // ── Derived display list ────────────────────────────────────────────────────
  const allMessages = messages.slice(0, 50);

  const unreadCount = allMessages.filter(
    (m) => !m.read_at && m.sender_id !== currentUserId
  ).length;

  const displayed = allMessages.filter((m) => {
    const isIncoming = m.sender_id !== currentUserId;
    if (filterTab === 'unread') return isIncoming && !m.read_at;
    if (filterTab === 'read')   return !isIncoming || !!m.read_at;
    return true;
  });

  // ── Default recipient for reply box ────────────────────────────────────────
  const lastIncoming = allMessages.find((m) => m.sender_id !== currentUserId);
  const defaultRecipientId   = quickReplyRecipientId ?? lastIncoming?.sender_id ?? null;
  const defaultRecipientName = quickReplyName || lastIncoming?.sender_name || '';

  // Who to send to
  const recipientId = composing ? selectedContactId : defaultRecipientId;

  // ── Send ────────────────────────────────────────────────────────────────────
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
      setSelectedContactId('');
      setQuickReplyMessageId(null);
      setQuickReplyRecipientId(null);
      setQuickReplyName('');
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
  const hasContacts = contactList.length > 0;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 360, bgcolor: '#F8FAFC', display: 'flex', flexDirection: 'column' } }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1, color: '#1E293B' }}>
          Mensajes
        </Typography>
        {hasContacts && (
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

      {/* ── Compose new message panel ───────────────────────────────────────── */}
      {composing && hasContacts && (
        <Box sx={{ px: 2, py: 1.5, bgcolor: '#FFF7ED', borderBottom: '1px solid #FED7AA', flexShrink: 0 }}>
          <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600, display: 'block', mb: 1 }}>
            Nuevo mensaje
          </Typography>
          <FormControl fullWidth size="small">
            <InputLabel sx={{ fontSize: '0.82rem' }}>Enviar a</InputLabel>
            <Select
              value={selectedContactId}
              label="Enviar a"
              onChange={(e) => setSelectedContactId(e.target.value)}
              sx={{ fontSize: '0.82rem' }}
            >
              {contactList.map((c) => (
                <MenuItem key={c.user_id} value={c.user_id} sx={{ fontSize: '0.82rem' }}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      {/* ── Filter tabs: Todos / No Leídas / Leídas ───────────────────────── */}
      <Box sx={{ bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0 }}>
        <Tabs
          value={filterTab}
          onChange={(_, v) => setFilterTab(v)}
          variant="fullWidth"
          sx={{
            minHeight: 36,
            '& .MuiTab-root': { minHeight: 36, fontSize: '0.75rem', fontWeight: 600, py: 0, textTransform: 'none' },
            '& .Mui-selected': { color: '#F57C00' },
            '& .MuiTabs-indicator': { bgcolor: '#F57C00' },
          }}
        >
          <Tab label="Todos" value="all" />
          <Tab
            label={unreadCount > 0 ? `No Leídas (${unreadCount})` : 'No Leídas'}
            value="unread"
          />
          <Tab label="Leídas" value="read" />
        </Tabs>
      </Box>

      {/* ── Message list — scrollable ───────────────────────────────────────── */}
      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {displayed.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              {filterTab === 'unread'
                ? 'Sin mensajes no leídos.'
                : filterTab === 'read'
                ? 'Sin mensajes leídos todavía.'
                : 'No tenés mensajes todavía.'}
            </Typography>
            {filterTab === 'all' && hasContacts && (
              <Button
                size="small"
                variant="outlined"
                sx={{ mt: 2, fontSize: '0.78rem', borderColor: '#F57C00', color: '#F57C00' }}
                onClick={() => setComposing(true)}
                startIcon={<EditIcon fontSize="small" />}
              >
                Escribir un mensaje
              </Button>
            )}
          </Box>
        ) : (
          <List disablePadding>
            {displayed.map((msg, idx) => {
              const isFromMe        = currentUserId && msg.sender_id === currentUserId;
              const isUnread        = !msg.read_at && !isFromMe;
              // Highlight only the SPECIFIC message the user clicked, not every message from same sender
              const isSelectedForReply = quickReplyMessageId === msg.id && !isFromMe;

              return (
                <React.Fragment key={msg.id}>
                  <ListItem
                    alignItems="flex-start"
                    onClick={!isFromMe ? () => {
                      setQuickReplyMessageId(msg.id);
                      setQuickReplyRecipientId(msg.sender_id);
                      setQuickReplyName(msg.sender_name);
                      setComposing(false);
                    } : undefined}
                    sx={{
                      px: 2,
                      py: 1.5,
                      bgcolor: isSelectedForReply
                        ? '#FFF7ED'       // selected for reply = orange tint
                        : isFromMe
                          ? '#F0FDF4'     // my message = green tint
                          : isUnread
                            ? '#FFFBEB'   // unread = amber
                            : 'white',
                      gap: 1,
                      justifyContent: isFromMe ? 'flex-end' : 'flex-start',
                      cursor: !isFromMe ? 'pointer' : 'default',
                      borderLeft: isSelectedForReply ? '3px solid #F57C00' : '3px solid transparent',
                      '&:hover': !isFromMe ? { bgcolor: '#FFF7ED' } : {},
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

      {/* ── Reply / compose box — pinned at bottom ─────────────────────────── */}
      {(defaultRecipientId || (composing && selectedContactId)) && (
        <Box sx={{ px: 2, py: 1.5, bgcolor: 'white', borderTop: '1px solid #E2E8F0', flexShrink: 0 }}>
          {/* "Respondiendo a X" hint */}
          {!composing && defaultRecipientName && (
            <Typography variant="caption" sx={{ color: '#F57C00', fontWeight: 600, display: 'block', mb: 0.5 }}>
              ↩ Respondiendo a {defaultRecipientName}
            </Typography>
          )}
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
              placeholder={composing ? 'Escribí tu mensaje...' : `Responderle a ${defaultRecipientName || 'tu coach'}...`}
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
