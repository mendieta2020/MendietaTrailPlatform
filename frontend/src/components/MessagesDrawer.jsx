/**
 * MessagesDrawer.jsx — PR-147 (v5 — session deep-link)
 *
 * Two-panel WhatsApp-style messaging:
 *
 * Panel 1 — Conversation list
 *   - One entry per contact, sorted by most recent
 *   - Unread badge per conversation
 *   - Tabs: Todos / No Leídas / Leídas
 *   - Compose pencil → new conversation with any contact
 *
 * Panel 2 — Thread view
 *   - Full chronological exchange with ONE person
 *   - Date separators: "Hoy", "Ayer", "Lunes 24 mar"
 *   - Read receipts: ✓ sent · ✓✓ orange = read (only on own messages)
 *   - Session deep-link: messages with alert_type="session_comment" show a
 *     "Ver sesión →" chip; tapping calls onSessionClick(reference_id, reference_date)
 *   - Auto-marks conversation as read on thread open
 *   - Reply box pinned at bottom (Enter to send, Shift+Enter = newline)
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
  Done as DoneIcon,
  DoneAll as DoneAllIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { sendMessage, markMessageRead } from '../api/messages';

// ── Helpers ──────────────────────────────────────────────────────────────────

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

const AVATAR_COLORS = ['#00D4AA', '#2563EB', '#059669', '#7C3AED', '#DC2626', '#0891B2'];
function avatarColor(name = '') {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

/** Returns a label like "Hoy", "Ayer", or "lunes 24 mar" */
function dateSeparatorLabel(isoString) {
  const date = new Date(isoString);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return 'Hoy';
  if (date.toDateString() === yesterday.toDateString()) return 'Ayer';
  return date.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'short' });
}

function isSameDay(a, b) {
  const da = new Date(a);
  const db = new Date(b);
  return (
    da.getFullYear() === db.getFullYear() &&
    da.getMonth() === db.getMonth() &&
    da.getDate() === db.getDate()
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

const MessagesDrawer = ({
  open,
  onClose,
  messages,
  contacts = [],
  coaches,            // legacy alias
  orgId,
  currentUserId,
  onMessageSent,
  onSessionClick,     // (referenceId, referenceDate, contactId) → void
}) => {
  const contactList = contacts.length > 0 ? contacts : (coaches ?? []);

  // ── Navigation ────────────────────────────────────────────────────────────
  const [view, setView] = useState('list');
  const [activeContactId, setActiveContactId] = useState(null);
  const [activeContactName, setActiveContactName] = useState('');

  // ── List state ────────────────────────────────────────────────────────────
  const [filterTab, setFilterTab] = useState('all');
  const [composing, setComposing] = useState(false);
  const [newContactId, setNewContactId] = useState('');

  // ── Thread state ──────────────────────────────────────────────────────────
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const threadBottomRef = useRef(null);

  // Reset on close
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

  // Scroll to bottom when entering thread or new messages arrive
  useEffect(() => {
    if (view === 'thread') {
      setTimeout(() => threadBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 80);
    }
  }, [view, messages]);

  // ── Conversation grouping ─────────────────────────────────────────────────
  const conversations = useMemo(() => {
    const map = {};
    messages.forEach((msg) => {
      const isFromMe  = msg.sender_id === currentUserId;
      const otherId   = isFromMe ? msg.recipient_id   : msg.sender_id;
      const otherName = isFromMe ? (msg.recipient_name ?? '') : (msg.sender_name ?? '');

      if (!map[otherId]) {
        map[otherId] = { contactId: otherId, contactName: otherName, messages: [], unreadCount: 0, lastAt: msg.created_at };
      }
      map[otherId].messages.push(msg);
      if (!msg.read_at && !isFromMe) map[otherId].unreadCount++;
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

  // Thread messages — chronological (oldest → newest, so newest is at bottom)
  const threadMessages = useMemo(() => {
    if (!activeContactId) return [];
    const conv = conversations.find((c) => c.contactId === activeContactId);
    return (conv?.messages ?? []).slice().sort((a, b) => (a.created_at > b.created_at ? 1 : -1));
  }, [conversations, activeContactId]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const openThread = (contactId, contactName) => {
    // Auto-mark all unread messages from this contact as read
    const conv = conversations.find((c) => c.contactId === contactId);
    if (conv && orgId) {
      const unread = conv.messages.filter((m) => !m.read_at && m.sender_id !== currentUserId);
      if (unread.length > 0) {
        Promise.all(unread.map((m) => markMessageRead(orgId, m.id).catch(() => {}))).then(() => {
          onMessageSent?.(); // Refresh once after all are marked
        });
      }
    }
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
    if (!replyText.trim() || !activeContactId || !orgId) return;
    setSending(true);
    setReplyError('');
    try {
      await sendMessage(orgId, {
        recipient_id: activeContactId,
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

  // ── Header ────────────────────────────────────────────────────────────────

  const renderHeader = () => {
    if (view === 'thread') {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', px: 1.5, py: 1.25, bgcolor: 'white', borderBottom: '1px solid #E2E8F0', flexShrink: 0, gap: 0.5 }}>
          <IconButton size="small" onClick={() => setView('list')} sx={{ color: '#64748B' }}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
          <Avatar sx={{ width: 30, height: 30, fontSize: '0.72rem', fontWeight: 700, bgcolor: avatarColor(activeContactName), mx: 0.5 }}>
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
            <Box component="span" sx={{ ml: 1, bgcolor: '#00D4AA', color: 'white', borderRadius: '10px', px: 0.8, py: 0.1, fontSize: '0.68rem', fontWeight: 700, verticalAlign: 'middle' }}>
              {totalUnread}
            </Box>
          )}
        </Typography>
        {hasContacts && (
          <IconButton
            size="small"
            title="Nuevo mensaje"
            onClick={() => setComposing((v) => !v)}
            sx={{ color: composing ? '#00D4AA' : '#64748B', mr: 0.5 }}
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

  // ── Panel 1: Conversation list ────────────────────────────────────────────

  const renderList = () => (
    <>
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
            fullWidth size="small" variant="contained"
            disabled={!newContactId}
            onClick={startNewConversation}
            sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00BF99' }, fontSize: '0.78rem', textTransform: 'none' }}
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
            '& .Mui-selected': { color: '#00D4AA' },
            '& .MuiTabs-indicator': { bgcolor: '#00D4AA' },
          }}
        >
          <Tab label="Todos" value="all" />
          <Tab label={totalUnread > 0 ? `No Leídas (${totalUnread})` : 'No Leídas'} value="unread" />
          <Tab label="Leídas" value="read" />
        </Tabs>
      </Box>

      <Box sx={{ flex: 1, overflowY: 'auto' }}>
        {filteredConversations.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              {filterTab === 'unread' ? 'Sin mensajes no leídos.' : filterTab === 'read' ? 'Sin conversaciones leídas.' : 'Sin conversaciones todavía.'}
            </Typography>
            {filterTab === 'all' && hasContacts && (
              <Button size="small" variant="outlined"
                sx={{ mt: 2, fontSize: '0.78rem', borderColor: '#00D4AA', color: '#00D4AA', textTransform: 'none' }}
                onClick={() => setComposing(true)} startIcon={<EditIcon fontSize="small" />}
              >
                Iniciar conversación
              </Button>
            )}
          </Box>
        ) : (
          <List disablePadding>
            {filteredConversations.map((conv, idx) => {
              const lastMsg = conv.messages[0]; // newest first from API
              const isLastFromMe = lastMsg?.sender_id === currentUserId;
              const preview = lastMsg?.content ?? '';

              return (
                <React.Fragment key={conv.contactId}>
                  <ListItem disablePadding>
                    <ListItemButton
                      onClick={() => openThread(conv.contactId, conv.contactName)}
                      sx={{
                        px: 2, py: 1.25,
                        bgcolor: conv.unreadCount > 0 ? '#FFFBEB' : 'white',
                        '&:hover': { bgcolor: '#F8FAFC' },
                        alignItems: 'center',
                      }}
                    >
                      <ListItemAvatar sx={{ minWidth: 48 }}>
                        <Badge
                          badgeContent={conv.unreadCount > 0 ? conv.unreadCount : null}
                          color="error" overlap="circular"
                          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
                        >
                          <Avatar sx={{ width: 40, height: 40, fontSize: '0.82rem', fontWeight: 700, bgcolor: avatarColor(conv.contactName) }}>
                            {avatarLetters(conv.contactName)}
                          </Avatar>
                        </Badge>
                      </ListItemAvatar>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                            <Typography variant="body2" sx={{ fontWeight: conv.unreadCount > 0 ? 700 : 500, color: '#1E293B', fontSize: '0.875rem' }}>
                              {conv.contactName}
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#9CA3AF', flexShrink: 0, ml: 1 }}>
                              {timeAgo(conv.lastAt)}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          <Typography variant="caption" sx={{
                            color: conv.unreadCount > 0 ? '#374151' : '#9CA3AF',
                            fontWeight: conv.unreadCount > 0 ? 600 : 400,
                            display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 210,
                          }}>
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

  // ── Panel 2: Thread view ──────────────────────────────────────────────────

  const renderThread = () => (
    <>
      <Box sx={{ flex: 1, overflowY: 'auto', py: 1.5, bgcolor: '#F8FAFC' }}>
        {threadMessages.length === 0 ? (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Empezá la conversación con {activeContactName}.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, px: 1.5 }}>
            {threadMessages.map((msg, idx) => {
              const isFromMe  = msg.sender_id === currentUserId;
              const isRead    = !!msg.read_at;

              // Date separator: show when this message is on a different day than the previous one
              const prevMsg = threadMessages[idx - 1];
              const showDateSep = idx === 0 || !isSameDay(msg.created_at, prevMsg.created_at);

              return (
                <React.Fragment key={msg.id}>
                  {/* ── Date separator ── */}
                  {showDateSep && (
                    <Box sx={{ display: 'flex', justifyContent: 'center', my: 1 }}>
                      <Typography variant="caption" sx={{
                        bgcolor: '#E2E8F0', color: '#64748B', borderRadius: '10px',
                        px: 1.5, py: 0.25, fontSize: '0.7rem', fontWeight: 600, textTransform: 'capitalize',
                      }}>
                        {dateSeparatorLabel(msg.created_at)}
                      </Typography>
                    </Box>
                  )}

                  {/* ── Message bubble ── */}
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: isFromMe ? 'flex-end' : 'flex-start' }}>
                    <Box sx={{
                      maxWidth: '82%',
                      bgcolor: isFromMe ? '#00D4AA' : 'white',
                      color: isFromMe ? 'white' : '#1E293B',
                      borderRadius: isFromMe ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                      px: 1.5, py: 0.875,
                      boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
                    }}>
                      <Typography variant="body2" sx={{ fontSize: '0.84rem', lineHeight: 1.45, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {msg.content}
                      </Typography>

                      {/* Session deep-link chip */}
                      {(msg.alert_type === 'session_comment' || msg.alert_type === 'athlete_session_note') && msg.reference_id && onSessionClick && (
                        <Box
                          onClick={() => {
                            onClose();
                            onSessionClick(msg.reference_id, msg.reference_date, activeContactId);
                          }}
                          sx={{
                            display: 'inline-flex', alignItems: 'center', gap: 0.4,
                            mt: 0.75, cursor: 'pointer',
                            bgcolor: isFromMe ? 'rgba(255,255,255,0.2)' : '#F1F5F9',
                            borderRadius: '8px', px: 1, py: 0.3,
                            '&:hover': { bgcolor: isFromMe ? 'rgba(255,255,255,0.3)' : '#E2E8F0' },
                          }}
                        >
                          <OpenInNewIcon sx={{ fontSize: '0.72rem', color: isFromMe ? 'rgba(255,255,255,0.9)' : '#00D4AA' }} />
                          <Typography variant="caption" sx={{ fontSize: '0.72rem', fontWeight: 600, color: isFromMe ? 'rgba(255,255,255,0.9)' : '#00D4AA' }}>
                            Ver sesión
                          </Typography>
                        </Box>
                      )}
                    </Box>

                    {/* Timestamp + read receipt (only on sent messages) */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, mt: 0.25, mx: 0.5 }}>
                      <Typography variant="caption" sx={{ color: '#9CA3AF', fontSize: '0.67rem' }}>
                        {timeAgo(msg.created_at)}
                      </Typography>
                      {isFromMe && (
                        isRead ? (
                          <DoneAllIcon sx={{ fontSize: '0.85rem', color: '#00D4AA' }} titleAccess="Leído" />
                        ) : (
                          <DoneIcon sx={{ fontSize: '0.85rem', color: '#CBD5E1' }} titleAccess="Enviado" />
                        )
                      )}
                    </Box>
                  </Box>
                </React.Fragment>
              );
            })}
            <div ref={threadBottomRef} />
          </Box>
        )}
      </Box>

      {/* Reply box */}
      <Box sx={{ px: 2, py: 1.5, bgcolor: 'white', borderTop: '1px solid #E2E8F0', flexShrink: 0 }}>
        {replyError && (
          <Typography variant="caption" color="error" sx={{ display: 'block', mb: 0.5 }}>
            {replyError}
          </Typography>
        )}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <TextField
            fullWidth multiline maxRows={4} size="small"
            placeholder={`Escribirle a ${activeContactName}...`}
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
            }}
            sx={{ '& .MuiOutlinedInput-root': { fontSize: '0.82rem', borderRadius: 2 } }}
          />
          <IconButton
            onClick={handleSend}
            disabled={sending || !canSend}
            size="small"
            sx={{
              bgcolor: '#00D4AA', color: 'white',
              '&:hover': { bgcolor: '#00BF99' },
              '&.Mui-disabled': { bgcolor: '#E5E7EB', color: '#9CA3AF' },
              width: 36, height: 36, flexShrink: 0,
            }}
          >
            {sending ? <CircularProgress size={16} color="inherit" /> : <SendIcon fontSize="small" />}
          </IconButton>
        </Box>
      </Box>
    </>
  );

  // ── Root render ───────────────────────────────────────────────────────────

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
