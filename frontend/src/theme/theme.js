import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light', // Fondo claro profesional
    primary: {
      main: '#00D4AA', // 🌊 QUANTORYN TEAL (Brand Color)
      contrastText: '#0D1117',
    },
    secondary: {
      main: '#0D1117', // Fondo oscuro (Para barras laterales)
    },
    background: {
      default: '#f3f4f6', // Gris muy suave (para que resalten las tarjetas blancas)
      paper: '#ffffff',   // Blanco puro para las tarjetas
    },
    text: {
      primary: '#0D1117',
      secondary: '#6E7781',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 700 },
    h2: { fontWeight: 700 },
    h3: { fontWeight: 600 },
    h4: { fontWeight: 600, fontSize: '1.5rem' },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  shape: {
    borderRadius: 16, // 🖌️ BORDES REDONDEADOS (Estilo Widget que te gustó)
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none', // Botones con texto normal (no todo mayúsculas)
          fontWeight: 600,
          borderRadius: 12, // Botones bien redondos
          boxShadow: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          boxShadow: '0px 4px 20px rgba(0, 0, 0, 0.05)', // Sombra suave "Flotante"
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        notchedOutline: {
          // CssBaseline (and any external CSS reset) sets fieldset border: 0.
          // Explicitly restoring border-width here ensures MUI OutlinedInput
          // borders are always visible regardless of CSS injection order.
          borderWidth: '1px',
        },
      },
    },
  },
});

export default theme;