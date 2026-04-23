"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { client } from "@/lib/api-client";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
}

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (email: string, password: string, full_name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const { data } = await client.GET("/api/v1/auth/me");
      if (data?.data) {
        setUser(data.data as User);
      } else {
        localStorage.removeItem("access_token");
        setUser(null);
      }
    } catch {
      localStorage.removeItem("access_token");
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchUser();
  }, [fetchUser]);

  const login = useCallback(async (email: string, password: string, rememberMe?: boolean) => {
    const params = new URLSearchParams();
    params.set("username", email);
    params.set("password", password);
    if (rememberMe) params.set("remember_me", "true");

    const { data } = await client.POST("/api/v1/auth/login", {
       
      // biome-ignore lint/suspicious/noExplicitAny: URLSearchParams body for form-encoded login, schema expects JSON shape
      body: params as any,
      bodySerializer: () => params,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    if (!data) throw new Error("Login failed");
    const envelope = data as { data?: { access_token: string }; access_token?: string };
    const token = envelope.data?.access_token ?? envelope.access_token;
    if (!token) throw new Error("Login failed");
    localStorage.setItem("access_token", token);

    const { data: meData } = await client.GET("/api/v1/auth/me");
    if (meData?.data) {
      setUser(meData.data as User);
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string, full_name: string) => {
      await client.POST("/api/v1/auth/register", {
        body: { email, password, full_name },
      });
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    setUser(null);
    window.location.href = "/auth/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // Fallback for components rendered outside provider (e.g. tests)
    // Returns a safe no-op default
    return {
      user: null,
      isLoading: true,
       
      // biome-ignore lint/suspicious/noEmptyBlockStatements: safe no-op fallback outside provider (e.g. tests)
      login: async () => {},
       
      // biome-ignore lint/suspicious/noEmptyBlockStatements: safe no-op fallback outside provider (e.g. tests)
      register: async () => {},
       
      // biome-ignore lint/suspicious/noEmptyBlockStatements: safe no-op fallback outside provider (e.g. tests)
      logout: () => {},
    };
  }
  return ctx;
}
