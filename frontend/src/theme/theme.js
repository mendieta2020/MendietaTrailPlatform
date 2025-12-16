import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light', // Fondo claro profesional
    primary: {
      main: '#F57C00', // 🔥 NARANJA MENDIETA (Color del Logo)
      contrastText: '#fff',
    },
    secondary: {
      main: '#1A2027', // Azul Oscuro Profundo (Para barras laterales)
    },
    background: {
      default: '#f3f4f6', // Gris muy suave (para que resalten las tarjetas blancas)
      paper: '#ffffff',   // Blanco puro para las tarjetas
    },
    text: {
      primary: '#1A2027',
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
  },
});

export default theme;