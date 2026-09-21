/**
 * Authentication Context and State Management with Session Persistence.
 * Reference: SIH26183, MHA / I4C.
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, OfficerProfile } from './api';
import { supabase, isSupabaseConfigured } from './supabase';

interface AuthContextType {
  officer: OfficerProfile | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (
    email: string,
    password: string,
    fullName: string,
    badgeNo?: string,
    district?: string,
  ) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = 'cryptotrace_sentinel_token';
const OFFICER_KEY = 'cryptotrace_sentinel_officer';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [officer, setOfficer] = useState<OfficerProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Restore session on mount (In-memory with sessionStorage restore as per Phase 6)
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // 1. If Supabase is connected with real credentials, check session
        if (isSupabaseConfigured) {
          const { data } = await supabase.auth.getSession();
          if (data.session) {
            const jwt = data.session.access_token;
            setToken(jwt);
            try {
              const profile = await api.getMe(jwt);
              setOfficer(profile);
              sessionStorage.setItem(TOKEN_KEY, jwt);
              sessionStorage.setItem(OFFICER_KEY, JSON.stringify(profile));
              setIsLoading(false);
              return;
            } catch (err) {
              console.warn('Could not fetch profile from backend with Supabase token:', err);
            }
          }
        }

        // 2. Check sessionStorage (in-memory token with session-level restore)
        const storedToken = sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
        const storedOfficer = sessionStorage.getItem(OFFICER_KEY) || localStorage.getItem(OFFICER_KEY);

        if (storedToken && storedOfficer) {
          try {
            const parsedOfficer = JSON.parse(storedOfficer);
            setToken(storedToken);
            api.setToken(storedToken);
            setOfficer(parsedOfficer);
            sessionStorage.setItem(TOKEN_KEY, storedToken);
            sessionStorage.setItem(OFFICER_KEY, storedOfficer);

            // Background refresh to confirm token is still valid
            api.getMe(storedToken)
              .then((freshProfile) => {
                setOfficer(freshProfile);
                sessionStorage.setItem(OFFICER_KEY, JSON.stringify(freshProfile));
              })
              .catch((err) => {
                console.warn('Session expired or invalidated:', err);
                if (String(err).includes('401')) {
                  logout();
                }
              });
          } catch {
            sessionStorage.removeItem(TOKEN_KEY);
            sessionStorage.removeItem(OFFICER_KEY);
            api.setToken(null);
          }
        }
      } finally {
        setIsLoading(false);
      }
    };

    initializeAuth();
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      if (isSupabaseConfigured) {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          console.warn('Supabase sign-in error, trying backend direct auth:', error.message);
        } else if (data.session) {
          const jwt = data.session.access_token;
          api.setToken(jwt);
          const profile = await api.getMe(jwt);
          setToken(jwt);
          setOfficer(profile);
          sessionStorage.setItem(TOKEN_KEY, jwt);
          sessionStorage.setItem(OFFICER_KEY, JSON.stringify(profile));
          return;
        }
      }

      // Default / Offline direct backend authentication
      const res = await api.login(email, password);
      setToken(res.access_token);
      api.setToken(res.access_token);
      setOfficer(res.officer);
      sessionStorage.setItem(TOKEN_KEY, res.access_token);
      sessionStorage.setItem(OFFICER_KEY, JSON.stringify(res.officer));
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (
    email: string,
    password: string,
    fullName: string,
    badgeNo?: string,
    district?: string,
  ) => {
    setIsLoading(true);
    try {
      if (isSupabaseConfigured) {
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { full_name: fullName, badge_no: badgeNo, district, role: 'INVESTIGATOR' },
          },
        });
        if (error) {
          console.warn('Supabase sign-up error, falling back to direct API:', error.message);
        }
      }

      // Direct backend signup (creates row in profiles with INVESTIGATOR role)
      const res = await api.signup(email, password, fullName, badgeNo, district);
      setToken(res.access_token);
      api.setToken(res.access_token);
      setOfficer(res.officer);
      sessionStorage.setItem(TOKEN_KEY, res.access_token);
      sessionStorage.setItem(OFFICER_KEY, JSON.stringify(res.officer));
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    if (isSupabaseConfigured) {
      supabase.auth.signOut().catch(console.warn);
    }
    setToken(null);
    api.setToken(null);
    setOfficer(null);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(OFFICER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(OFFICER_KEY);
  };

  const refreshProfile = async () => {
    if (!token) return;
    try {
      const fresh = await api.getMe(token);
      setOfficer(fresh);
      localStorage.setItem(OFFICER_KEY, JSON.stringify(fresh));
    } catch (err) {
      console.warn('Failed to refresh officer profile:', err);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        officer,
        token,
        isLoading,
        login,
        signup,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
