/**
 * MessagesDrawer.jsx — PR-147 (v3 — WhatsApp-style)
 *
 * Two-panel messaging experience:
 *
 * Panel 1 — Conversation list:
 *   - One entry per contact (grouped by the OTHER person in the thread)
 *   - Shows: avatar letter, name, last message preview, timestamp, unread badge
 *   - Tabs: Todos / No Leídas / Leídas
 *   - Compose button (pencil) → new conversation with any contact
 *
 * Panel 2 — Thread view (after tapping a conversation):
 *   - Full chronological exchange with that ONE person
 *   - Back button returns to list
 *   - Reply box pinned at bottom
 *
 * Works for BOTH coach (contacts = athletes) and athlete (contacts = coaches).
 */

import React, { useState, useMemo, useEffect, useRef } from 'react';
import {
  Box,
  Drawer,
  Typography,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemAvatar,
  ListItemText,
  Avatar,
  TextField,
  Button,
  CircularProgress,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Tab,
  Tabs,
  Badge,
} from '@mui/material';
import {
  Close as CloseIcon,
  Send as SendIcon,
  Edit as EditIcon,
  ArrowBack as ArrowBackIcon,
} from '@mui/icons-material';
import { sendMessage } from '../api/messages';

// ── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days}d`;
}

function avatarLetters(name = '') {
  const parts = name.trim().split(' ').filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? '?').toUpperCase();
}

// Derive a stable background color for each contact from their name
const AVATAR_COLORS = ['#F57C00', '#2563EB', '#059669', '#7C3AED', '#DC2626', '#0891B2'];
function avatarColor(name = '') {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

// ── Component ────────────────────────────────────────────────────────────────

const MessagesDrawer = ({
  open,
  onClose,
  messages,
  contacts = [],
  coaches,           // legacy alias
  orgId,
  currentUserId,
  onMessageSent,
}) => {
  const contactList = contacts.length > 0 ? contacts : (coaches ?? []);

  // ── Navigation state ──────────────────────────────────────────────────────
  const [view, setView] = useState('list');          // 'list' | 'thread'
  const [activeContactId, setActiveContactId] = useState(null);
  const [activeContactName, setActiveContactName] = useState('');

  // ── List-level state ──────────────────────────────────────────────────────
  const [filterTab, setFilterTab] = useState('all');
  const [composing, setComposing] = useState(false);
  const [newContactId, setNewContactId] = useState('');

  // ── Thread-level state ────────────────────────────────────────────────────
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const threadBottomRef = useRef(null);

  // Reset to list when drawer is closed
  useEffect(() => {
    if (!open) {
      setView('list');
      setActiveContactId(null);
      setActiveContactName('');
      setComposing(false);
      setNewContactId('');
      setReplyText('');
      setReplyError('');
    }
  }, [open]);

  // Scroll to bottom of thread on open / new messages
  useEffect(() => {
    if (view === 'thread') {
      setTimeout(() => threadBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 80);
    }
  }, [view, messages]);

  // ── Conversation grouping ─────────────────────────────────────────────────
  const conversations = useMemo(() => {
    const map = {};
    messages.forEach((msg) => {
      const isFromMe = msg.sender_id === currentUserId;
      const otherId   = isFromMe ? msg.recipient_id   : msg.sender_id;
      const otherName = isFromMe ? (msg.recipient_name ?? '') : (msg.sender_name ?? '');

      if (!map[otherId]) {
        map[otherId] = {
          contactId:   otherId,
          contactName: otherName,
          messages:    [],
          unreadCount: 0,
          lastAt:      msg.created_at,
        };
      }
      map[otherId].messages.push(msg);
      if (!msg.read_at && !isFromMe) map[otherId].unreadCount++;
      // keep most-recent timestamp
      if (msg.created_at > map[otherId].lastAt) map[otherId].lastAt = msg.created_at;
    });

    return Object.values(map).sort((a, b) => (b.lastAt > a.lastAt ? 1 : -1));
  }, [messages, currentUserId]);

  const totalUnread = conversations.reduce((s, c) => s + c.unreadCount, 0);

  const filteredConversations = conversations.filter((c) => {
    if (filterTab === 'unread') return c.unreadCount > 0;
    if (filterTab === 'read')   return c.unreadCount === 0;
    return true;
  });

  // Active thread messages — chronological (oldest first, newest at bottom)
  const threadMessages = useMemo(() => {
    if (!activeContactId) return [];
    const conv = conversations.find((c) => c.contactId === activeContactId);
    return (conv?.messages ?? []).slice().sort((a, b) => (a.created_at > b.created_at ? 1 : -1));
  }, [conversations, activeContactId]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const openThread = (contactId, contactName) => {
    setActiveContactId(contactId);
    setActiveContactName(contactName);
    setReplyText('');
    setReplyError('');
    setView('thread');
  };

  const startNewConversation = () => {
    if (!newContactId) return;
    const contact = contactList.find((c) => c.user_id === newContactId);
    setComposing(false);
    setNewContactId('');
    openThread(newContactId, contact?.name ?? '');
  };

  const handleSend = async () => {
    const recipientId = view === 'thread' ? activeContactId : null;
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
      onMessageSent?.();
    } catch (err) {
      const data = err?.response?.data;
      const detail = data?.detail || data?.recipient_id || 'Error al enviar. Intentá de nuevo.';
      setReplyError(Array.isArray(detail) ? detail[0] : detail);
    } finally {
      setSending(false);
    }
  };

  const canSend = !!(activeContactId && replyText.trim() && orgId);
  const hasContacts = contactList.length > 0;

  // ── Render helpers ────────────────────────────────────────────────────────

  const renderHeader = () => {
    if (view === 'thread') {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', px: 1.5, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0, gap: 0.5 }}>
          <IconButton size="small" onClick={() => setView('list')} sx={{ color: '#64748B' }}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
          <Avatar
            sx={{ width: 30, height: 30, fontSize: '0.72rem', fontWeight: 700, bgcolor: avatarColor(activeContactName), mx: 0.5 }}
          >
            {avatarLetters(activeContactName)}
          </Avatar>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1E293B', flexGrow: 1, fontSize: '0.9rem' }}>
            {activeContactName}
          </Typography>
          <IconButton onClick={onClose} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      );
    }

    return (
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1, color: '#1E293B' }}>
          Mensajes
          {totalUnread > 0 && (
            <Box component="span" sx={{ ml: 1, bgcolor: '#F57C00', color: 'white', borderRadius: '10px', px: 0.8, py: 0.1, fontSize: '0.68rem', fontWeight: 700, verticalAlign: 'middle' }}>
              {totalUnread}
            </Box>
          )}
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
    );
  };

  // ── Conversation list view ────────────────────────────────────────────────

  const renderList = () => (
    <>
      {/* New message compose panel */}
      {composing && hasContacts && (
        <Box sx={{ px: 2, py: 1.5, bgcolor: '#FFF7ED', borderBottom: '1px solid #FED7AA', flexShrink: 0 }}>
          <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600, display: 'block', mb: 1 }}>
            Nueva conversación
          </Typography>
          <FormControl fullWidth size="small" sx={{ mb: 1 }}>
            <InputLabel sx={{ fontSize: '0.82rem' }}>Enviar a</InputLabel>
            <Select
              value={newContactId}
              label="Enviar a"
              onChange={(e) => setNewContactId(e.target.value)}
              sx={{ fontSize: '0.82rem' }}
            >
              {contactList.map((c) => (
                <MenuItem key={c.user_id} value={c.user_id} sx={{ fontSize: '0.82rem' }}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            fullWidth
            size="small"
            variant="contained"
            disabled={!newContactId}
            onClick={startNewConversation}
            sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#E65100' }, fontSize: '0.78rem', textTransform: 'none' }}
          >
            Abrir conversación
          </Button>
        </Box>
      )}

      {/* Filter tabs */}
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
          <Tab label={totalUnread > 0 ? `No Leídas (${totalUnread})` : 'No Leídas'} value="unread" />
          <Tab label="Leídas" value="read" />
        </Tabs>
      </Box>

      {/* Conversation list */}
      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {filteredConversations.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              {filterTab === 'unread' ? 'Sin mensajes no leídos.' : filterTab === 'read' ? 'Sin conversaciones leídas.' : 'Sin conversaciones todavía.'}
            </Typography>
            {filterTab === 'all' && hasContacts && (
              <Button
                size="small"
                variant="outlined"
                sx={{ mt: 2, fontSize: '0.78rem', borderColor: '#F57C00', color: '#F57C00', textTransform: 'none' }}
                onClick={() => setComposing(true)}
                startIcon={<EditIcon fontSize="small" />}
              >
                Iniciar conversación
              </Button>
            )}
          </Box>
        ) : (
          <List disablePadding>
            {filteredConversations.map((conv, idx) => {
              // Last message for preview
              const lastMsg = conv.messages[0]; // messages are newest-first from API
              const isLastFromMe = lastMsg?.sender_id === currentUserId;
              const preview = lastMsg?.content ?? '';

              return (
                <React.Fragment key={conv.contactId}>
                  <ListItem disablePadding>
                    <ListItemButton
                      onClick={() => openThread(conv.contactId, conv.contactName)}
                      sx={{
                        px: 2,
                        py: 1.25,
                        bgcolor: conv.unreadCount > 0 ? '#FFFBEB' : 'white',
                        '&:hover': { bgcolor: '#F8FAFC' },
                        alignItems: 'center',
                      }}
                    >
                      <ListItemAvatar sx={{ minWidth: 46 }}>
                        <Badge
                          badgeContent={conv.unreadCount > 0 ? conv.unreadCount : null}
                          color="error"
                          overlap="circular"
                          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
                        >
                          <Avatar
                            sx={{
                              width: 38,
                              height: 38,
                              fontSize: '0.82rem',
                              fontWeight: 700,
                              bgcolor: avatarColor(conv.contactName),
                            }}
                          >
                            {avatarLetters(conv.contactName)}
                          </Avatar>
                        </Badge>
                      </ListItemAvatar>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                            <Typography
                              variant="body2"
                              sx={{ fontWeight: conv.unreadCount > 0 ? 700 : 500, color: '#1E293B', fontSize: '0.875rem' }}
                            >
                              {conv.contactName}
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#9CA3AF', flexShrink: 0, ml: 1 }}>
                              {timeAgo(conv.lastAt)}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          <Typography
                            variant="caption"
                            sx={{
                              color: conv.unreadCount > 0 ? '#374151' : '#9CA3AF',
                              fontWeight: conv.unreadCount > 0 ? 600 : 400,
                              display: 'block',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: 220,
                            }}
                          >
                            {isLastFromMe ? 'Tú: ' : ''}{preview}
                          </Typography>
                        }
                        secondaryTypographyProps={{ component: 'div' }}
                      />
                    </ListItemButton>
                  </ListItem>
                  {idx < filteredConversations.length - 1 && <Divider sx={{ borderColor: '#F1F5F9' }} />}
                </React.Fragment>
              );
            })}
          </List>
        )}
      </Box>
    </>
  );

  // ── Thread view ───────────────────────────────────────────────────────────

  const renderThread = () => (
    <>
      {/* Messages — scrollable, chronological */}
      <Box sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {threadMessages.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Empezá la conversación con {activeContactName}.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, px: 2 }}>
            {threadMessages.map((msg) => {
              const isFromMe = msg.sender_id === currentUserId;
              return (
                <Box
                  key={msg.id}
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isFromMe ? 'flex-end' : 'flex-start',
                  }}
                >
                  <Box
                    sx={{
                      maxWidth: '80%',
                      bgcolor: isFromMe ? '#F57C00' : 'white',
                      color: isFromMe ? 'white' : '#1E293B',
                      borderRadius: isFromMe ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                      px: 1.5,
                      py: 1,
                      boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
                    }}
                  >
                    <Typography variant="body2" sx={{ fontSize: '0.84rem', lineHeight: 1.4, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {msg.content}
                    </Typography>
                  </Box>
                  <Typography variant="caption" sx={{ color: '#9CA3AF', mt: 0.25, mx: 0.5, fontSize: '0.68rem' }}>
                    {timeAgo(msg.created_at)}
                  </Typography>
                </Box>
              );
            })}
            <div ref={threadBottomRef} />
          </Box>
        )}
      </Box>

      {/* Reply box — pinned at bottom */}
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
            maxRows={4}
            size="small"
            placeholder={`Escribirle a ${activeContactName}...`}
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
    </>
  );

  // ── Main render ───────────────────────────────────────────────────────────

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 360, bgcolor: '#F8FAFC', display: 'flex', flexDirection: 'column' } }}
    >
      {renderHeader()}
      {view === 'list' ? renderList() : renderThread()}
    </Drawer>
  );
};

export default MessagesDrawer;
