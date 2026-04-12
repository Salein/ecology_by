"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authLogout, getApiBase } from "@/lib/api";
import { clearLegacyAuthStorage, clearSessionGate, setSessionGate } from "@/lib/sessionGate";

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  created_at: string;
  blocked: boolean;
  protected_account?: boolean;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const cred = { credentials: "include" as const };

async function parseJsonError(r: Response): Promise<string> {
  try {
    const j = (await r.json()) as { detail?: string | unknown };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  return `Ошибка ${r.status}`;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/api/v1/auth/me`, { ...cred });
      if (!r.ok) {
        if (r.status === 401 || r.status === 403) {
          try {
            await authLogout();
          } catch {
            /* сеть */
          }
        }
        setUser(null);
        clearSessionGate();
        return;
      }
      const u = (await r.json()) as AuthUser;
      setUser(u);
      setSessionGate();
    } catch {
      setUser(null);
      clearSessionGate();
    }
  }, []);

  useEffect(() => {
    clearLegacyAuthStorage();
    void (async () => {
      setLoading(true);
      await refreshMe();
      setLoading(false);
    })();
  }, [refreshMe]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await fetch(`${getApiBase()}/api/v1/auth/login`, {
      ...cred,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (!r.ok) throw new Error(await parseJsonError(r));
    const data = (await r.json()) as { user: AuthUser };
    setUser(data.user);
    setSessionGate();
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const r = await fetch(`${getApiBase()}/api/v1/auth/register`, {
      ...cred,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password, name: name.trim() }),
    });
    if (!r.ok) throw new Error(await parseJsonError(r));
    const data = (await r.json()) as { user: AuthUser };
    setUser(data.user);
    setSessionGate();
  }, []);

  const logout = useCallback(async () => {
    try {
      await authLogout();
    } catch {
      /* сеть */
    }
    clearSessionGate();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      refreshMe,
    }),
    [user, loading, login, register, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}
