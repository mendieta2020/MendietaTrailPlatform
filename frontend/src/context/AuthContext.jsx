import { createContext, useState, useEffect, useContext } from 'react';
import api from '../api/axios'; // Usamos nuestra instancia configurada

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Al cargar, verificamos si ya existe un token guardado
        const checkAuth = async () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                // Si hay token, asumimos que el usuario es válido (el interceptor lo borrará si no)
                setUser({ username: 'Coach' }); 
            }
            setLoading(false);
        };
        checkAuth();
    }, []);

    const login = async (username, password) => {
        try {
            // Hacemos POST a la ruta de token de Django
            // IMPORTANTE: Esta ruta DEBE estar abierta (AllowAny) en el backend, 
            // pero como es JWT predeterminada, suele estarlo.
            const response = await api.post('token/', { username, password });
            
            // Guardamos las llaves
            localStorage.setItem('access_token', response.data.access);
            localStorage.setItem('refresh_token', response.data.refresh);
            
            setUser({ username });
            return { success: true };
        } catch (error) {
            console.error("Login fallido:", error);
            return { success: false, error: "Credenciales incorrectas o servidor no disponible." };
        }
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setUser(null);
        // Recargar la página para limpiar estados
        window.location.href = '/';
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);