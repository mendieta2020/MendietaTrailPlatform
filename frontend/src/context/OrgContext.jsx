/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { useAuth } from './AuthContext';

const SESSION_KEY = 'quantoryn_active_org_id';

const OrgContext = createContext(null);

const initialState = { activeOrgId: null, orgLoading: true };

function orgReducer(state, action) {
  switch (action.type) {
    case 'RESOLVE':
      return { activeOrgId: action.activeOrgId, orgLoading: false };
    case 'SET_ACTIVE':
      return { ...state, activeOrgId: action.orgId };
    default:
      return state;
  }
}

export function OrgProvider({ children }) {
  const { user, loading: authLoading } = useAuth();
  const [state, dispatch] = useReducer(orgReducer, initialState);

  useEffect(() => {
    if (authLoading) return;

    const userMemberships = user?.memberships ?? [];
    if (userMemberships.length === 0) {
      dispatch({ type: 'RESOLVE', activeOrgId: null });
      return;
    }

    const savedId = localStorage.getItem(SESSION_KEY);
    const saved = savedId
      ? userMemberships.find((m) => String(m.org_id) === savedId)
      : null;
    const resolved = saved ?? userMemberships[0];
    localStorage.setItem(SESSION_KEY, String(resolved.org_id));
    dispatch({ type: 'RESOLVE', activeOrgId: resolved.org_id });
  }, [user, authLoading]);

  const memberships = user?.memberships ?? [];
  const activeOrg =
    memberships.find((m) => m.org_id === state.activeOrgId) ?? null;

  function setActiveOrg(orgId) {
    const found = memberships.find((m) => m.org_id === orgId);
    if (!found) return;
    localStorage.setItem(SESSION_KEY, String(found.org_id));
    dispatch({ type: 'SET_ACTIVE', orgId });
  }

  return (
    <OrgContext.Provider
      value={{ activeOrg, memberships, setActiveOrg, orgLoading: state.orgLoading }}
    >
      {children}
    </OrgContext.Provider>
  );
}

export function useOrg() {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error('useOrg must be used inside OrgProvider');
  return ctx;
}
