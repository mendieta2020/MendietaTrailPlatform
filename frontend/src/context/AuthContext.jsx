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
                    const { data } = await fetchSession();
                    setUser(data);
                } catch {
                    setUser(null);
                } finally {
                    setLoading(false);
                }
                return;
            }

            const token = tokenStore.getAccessToken();
            if (token) {
                // PR-151 fix: fetch real session data (with memberships) instead of fake user
                try {
                    const { data } = await fetchSession();
                    setUser(data);
                } catch {
                    // Token expired or invalid — clear and set null
                    tokenStore.clear();
                    setUser(null);
                }
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
        setUser(null);
        try {
            await loginWithCredentials({ username, password });

            const { data } = await fetchSession();
            setUser(data);
            if (import.meta.env.DEV) {
                console.debug('[Auth] login success');
            }
            return { success: true };
        } catch (error) {
            if (import.meta.env.DEV) {
                console.debug('[Auth] login failed', error);
            }
            return { success: false, error: "Credenciales incorrectas o servidor no disponible." };
        }
    };

    // PR-149: Login with pre-obtained JWT tokens (post-registration)
    const loginWithTokens = async ({ access, refresh }) => {
        tokenStore.setTokens({ access, refresh });
        try {
            const { data } = await fetchSession();
            setUser(data);
        } catch {
            // Session endpoint may not return full data for a brand-new user.
            // Set minimal user object so auth guards pass; InvitePage controls
            // the flow and does not depend on memberships at this point.
            setUser({ username: 'NewAthlete', memberships: [] });
        }
        return { success: true };
    };

    const logout = () => {
        logoutSession();
        setUser(null);
        // Recargar la página para limpiar estados
        window.location.href = '/';
    };

    return (
        <AuthContext.Provider value={{ user, login, loginWithTokens, logout, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
