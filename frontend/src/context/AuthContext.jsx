/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect, useContext } from 'react';
import client from '../api/client'; // Instancia única (baseURL + interceptores)
import { tokenStore } from '../api/tokenStore';
import { subscribeOnLogout } from '../api/authEvents';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Al cargar, verificamos si ya existe un token guardado
        const checkAuth = async () => {
            const token = tokenStore.getAccessToken();
            if (token) {
                // Si hay token, asumimos que el usuario es válido (el interceptor lo borrará si no)
                setUser({ username: 'Coach' }); 
            }
            setLoading(false);
        };
        checkAuth();

        // Si el cliente fuerza logout (refresh fallido), reflejarlo en estado.
        const unsub = subscribeOnLogout(() => {
            setUser(null);
        });
        return () => unsub();
    }, []);

    const login = async (username, password) => {
        try {
            // Hacemos POST a la ruta de token de Django
            const response = await client.post('/api/token/', { username, password });
            
            // Guardamos las llaves
            tokenStore.setTokens({ access: response.data.access, refresh: response.data.refresh });
            
            setUser({ username });
            return { success: true };
        } catch (error) {
            console.error("Login fallido:", error);
            return { success: false, error: "Credenciales incorrectas o servidor no disponible." };
        }
    };

    const logout = () => {
        tokenStore.clear();
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