"use client";

import { createContext, useContext, useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";

export type ThemeContextValue = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolvedTheme: "light" | "dark";
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

// ---- helpers used by ThemeProvider ----

const STORAGE_KEY = "pingcrm-theme";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem(STORAGE_KEY) as Theme) || "system";
}

export function setStoredTheme(t: Theme) {
  localStorage.setItem(STORAGE_KEY, t);
}

export function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function resolveTheme(theme: Theme): "light" | "dark" {
  return theme === "system" ? getSystemTheme() : theme;
}

export function applyThemeToDOM(resolved: "light" | "dark") {
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

// Subscribe to system preference changes
let listeners: Array<() => void> = [];

function subscribe(cb: () => void) {
  listeners.push(cb);
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    listeners.forEach((l) => l());
  };
  mql.addEventListener("change", handler);
  return () => {
    listeners = listeners.filter((l) => l !== cb);
    mql.removeEventListener("change", handler);
  };
}

function getSnapshot(): "light" | "dark" {
  return getSystemTheme();
}

function getServerSnapshot(): "light" | "dark" {
  return "light";
}

export function useSystemTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
