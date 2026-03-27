/**
 * MessagesDrawer.jsx — PR-147
 *
 * Right-side drawer for the athlete showing coach messages.
 * Unread messages show amber background + orange dot.
 */

import React from 'react';
import {
  Box,
  Drawer,
  Typography,
  Divider,
  IconButton,
  List,
  ListItem,
} from '@mui/material';
import { Close as CloseIcon } from '@mui/icons-material';

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days} día${days !== 1 ? 's' : ''}`;
}

const MessagesDrawer = ({ open, onClose, messages }) => {
  const displayed = messages.slice(0, 20);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 360, bgcolor: '#F8FAFC' } }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E2E8F0' }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1, color: '#1E293B' }}>
          Mensajes de tu coach
        </Typography>
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Message list */}
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
            return (
              <React.Fragment key={msg.id}>
                <ListItem
                  alignItems="flex-start"
                  sx={{
                    px: 2,
                    py: 1.5,
                    bgcolor: isUnread ? '#FFFBEB' : 'white',
                    gap: 1,
                  }}
                >
                  {/* Unread dot */}
                  <Box sx={{ pt: '6px', minWidth: 10 }}>
                    {isUnread && (
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
                      <Typography variant="caption" sx={{ fontWeight: 700, color: '#374151' }}>
                        {msg.sender_name}
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
                        WebkitLineClamp: 3,
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
    </Drawer>
  );
};

export default MessagesDrawer;
