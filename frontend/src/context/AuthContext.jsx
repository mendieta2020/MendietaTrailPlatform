/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect, useContext } from 'react';
import { tokenStore } from '../api/tokenStore';
import { subscribeOnLogout } from '../api/authEvents';
import { USE_COOKIE_AUTH } from '../api/authMode';
import { fetchSession, loginWithCredentials, logoutSession } from '../api/authClient';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Al cargar, verificamos si ya existe un token guardado
        const checkAuth = async () => {
            if (USE_COOKIE_AUTH) {
                try {
                    const response = await fetchSession();
                    setUser(response.data);
                } catch (error) {
                    setUser(null);
                } finally {
                    setLoading(false);
                }
                return;
            }

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
            await loginWithCredentials({ username, password });

            setUser({ username });
            return { success: true };
        } catch (error) {
            console.error("Login fallido:", error);
            return { success: false, error: "Credenciales incorrectas o servidor no disponible." };
        }
    };

    const logout = () => {
        logoutSession();
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
