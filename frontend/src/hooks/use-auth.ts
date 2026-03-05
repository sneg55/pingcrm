"use client";

import { useState, useEffect, useCallback } from "react";
import apiClient from "@/lib/api";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
}

export function useAuth() {
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
      const { data } = await apiClient.get<{ data: User; error: string | null }>(
        "/auth/me"
      );
      setUser(data.data);
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

  const login = useCallback(async (email: string, password: string) => {
    const params = new URLSearchParams();
    params.set("username", email);
    params.set("password", password);

    const { data } = await apiClient.post<{ access_token: string }>(
      "/auth/login",
      params,
      { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
    );
    localStorage.setItem("access_token", data.access_token);

    const { data: meData } = await apiClient.get<{
      data: User;
      error: string | null;
    }>("/auth/me");
    setUser(meData.data);
  }, []);

  const register = useCallback(
    async (email: string, password: string, full_name: string) => {
      await apiClient.post("/auth/register", { email, password, full_name });
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    setUser(null);
    window.location.href = "/auth/login";
  }, []);

  return { user, isLoading, login, register, logout };
}
