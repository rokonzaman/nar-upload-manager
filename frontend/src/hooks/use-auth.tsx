"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearSession, getStoredUser, getToken, setSession } from "@/lib/api";
import type { TokenResponse, UserOut } from "@/lib/types";

interface AuthContextValue {
  user: UserOut | null;
  loading: boolean;
  isAdmin: boolean;
  isDeveloper: boolean;
  login: (username: string, password: string) => Promise<UserOut>;
  loginWithToken: (tokenResponse: TokenResponse) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    const stored = getStoredUser<UserOut>();
    if (stored) setUser(stored);
    api
      .get<UserOut>("/auth/me")
      .then((fresh) => {
        setUser(fresh);
        setSession(token, fresh);
      })
      .catch(() => clearSession())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await api.post<TokenResponse>("/auth/login", { username, password });
    setSession(response.access_token, response.user);
    setUser(response.user);
    return response.user;
  }, []);

  const loginWithToken = useCallback((response: TokenResponse) => {
    setSession(response.access_token, response.user);
    setUser(response.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* best effort */
    }
    clearSession();
    setUser(null);
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAdmin: user?.role === "admin",
      isDeveloper: user?.role === "admin" || user?.role === "developer",
      login,
      loginWithToken,
      logout,
    }),
    [user, loading, login, loginWithToken, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
