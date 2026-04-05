import React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import PublicLayout from '../../components/PublicLayout';
import MarkdownRenderer from '../../components/MarkdownRenderer';
import content from '../../content/security_policy.md?raw';

const SecurityPage = () => (
  <PublicLayout>
    <Box sx={{ maxWidth: 860, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 4, md: 8 } }}>
      <Typography
        variant="overline"
        sx={{ color: '#00D4AA', fontWeight: 700, letterSpacing: '0.1em', display: 'block', mb: 0.5 }}
      >
        Security
      </Typography>
      <MarkdownRenderer content={content} />
    </Box>
  </PublicLayout>
);

export default SecurityPage;
