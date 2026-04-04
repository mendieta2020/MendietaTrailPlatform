import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';

/**
 * Renders a raw markdown string using react-markdown + remark-gfm.
 * Styled with MUI components; no dangerouslySetInnerHTML.
 */
const MarkdownRenderer = ({ content }) => {
  const components = {
    h1: ({ children }) => (
      <Typography
        component="h1"
        variant="h4"
        sx={{ fontWeight: 700, mt: 4, mb: 1.5, color: 'text.primary' }}
      >
        {children}
      </Typography>
    ),
    h2: ({ children }) => (
      <Typography
        component="h2"
        variant="h5"
        sx={{ fontWeight: 700, mt: 4, mb: 1.5, color: 'text.primary', borderBottom: '2px solid #00D4AA', pb: 0.5 }}
      >
        {children}
      </Typography>
    ),
    h3: ({ children }) => (
      <Typography
        component="h3"
        variant="h6"
        sx={{ fontWeight: 600, mt: 3, mb: 1, color: 'text.primary' }}
      >
        {children}
      </Typography>
    ),
    h4: ({ children }) => (
      <Typography
        component="h4"
        variant="subtitle1"
        sx={{ fontWeight: 600, mt: 2.5, mb: 0.75, color: 'text.primary' }}
      >
        {children}
      </Typography>
    ),
    p: ({ children }) => (
      <Typography
        component="p"
        variant="body1"
        sx={{ mb: 1.5, lineHeight: 1.8, color: 'text.primary' }}
      >
        {children}
      </Typography>
    ),
    ul: ({ children }) => (
      <Box component="ul" sx={{ pl: 3, mb: 1.5, mt: 0 }}>
        {children}
      </Box>
    ),
    ol: ({ children }) => (
      <Box component="ol" sx={{ pl: 3, mb: 1.5, mt: 0 }}>
        {children}
      </Box>
    ),
    li: ({ children }) => (
      <Box component="li" sx={{ mb: 0.5 }}>
        <Typography component="span" variant="body1" sx={{ lineHeight: 1.8 }}>
          {children}
        </Typography>
      </Box>
    ),
    // Block code: override <pre> for the outer wrapper
    pre: ({ children }) => (
      <Box
        component="pre"
        sx={{
          bgcolor: '#0D1117',
          color: '#e8e8e8',
          borderRadius: 2,
          p: 2.5,
          my: 2,
          overflowX: 'auto',
          fontFamily: '"Fira Mono", "Cascadia Code", monospace',
          fontSize: '0.85em',
          lineHeight: 1.6,
          border: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        {children}
      </Box>
    ),
    // <code> — inline styling; inside <pre> the pre styling wins via CSS parent selector
    code: ({ children, className }) => (
      <Box
        component="code"
        className={className}
        sx={{
          fontFamily: '"Fira Mono", "Cascadia Code", monospace',
          fontSize: '0.875em',
          bgcolor: 'rgba(0, 212, 170,0.10)',
          color: '#b45309',
          px: '5px',
          py: '2px',
          borderRadius: '4px',
          // When inside a <pre>, the pre provides all styling — reset inline styles
          'pre &': {
            bgcolor: 'transparent',
            color: 'inherit',
            px: 0,
            py: 0,
            borderRadius: 0,
          },
        }}
      >
        {children}
      </Box>
    ),
    // Tables
    table: ({ children }) => (
      <Box sx={{ overflowX: 'auto', mb: 2 }}>
        <Box
          component="table"
          sx={{
            borderCollapse: 'collapse',
            width: '100%',
            fontSize: '0.9em',
            '& th, & td': {
              border: '1px solid #e0e0e0',
              px: 2,
              py: 1,
              textAlign: 'left',
              verticalAlign: 'top',
            },
            '& th': {
              bgcolor: '#f8f8f8',
              fontWeight: 600,
              color: 'text.primary',
            },
            '& tr:nth-of-type(even) td': {
              bgcolor: '#fafafa',
            },
          }}
        >
          {children}
        </Box>
      </Box>
    ),
    thead: ({ children }) => <thead>{children}</thead>,
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => <tr>{children}</tr>,
    th: ({ children }) => <th>{children}</th>,
    td: ({ children }) => <td>{children}</td>,
    hr: () => <Divider sx={{ my: 3 }} />,
    blockquote: ({ children }) => (
      <Box
        sx={{
          borderLeft: '4px solid #00D4AA',
          pl: 2,
          ml: 0,
          my: 2,
          color: 'text.secondary',
          fontStyle: 'italic',
        }}
      >
        {children}
      </Box>
    ),
    a: ({ href, children }) => (
      <Box
        component="a"
        href={href}
        sx={{
          color: '#00D4AA',
          textDecoration: 'none',
          fontWeight: 500,
          '&:hover': { textDecoration: 'underline' },
        }}
      >
        {children}
      </Box>
    ),
    strong: ({ children }) => (
      <Box component="strong" sx={{ fontWeight: 700 }}>
        {children}
      </Box>
    ),
    em: ({ children }) => (
      <Box component="em" sx={{ fontStyle: 'italic' }}>
        {children}
      </Box>
    ),
  };

  return (
    <Box sx={{ maxWidth: '100%', overflowX: 'hidden', wordBreak: 'break-word' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </Box>
  );
};

export default MarkdownRenderer;
