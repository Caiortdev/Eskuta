/**
 * Theme system — light/dark/system. Persistido em localStorage.
 *
 * Tailwind v4 com `@custom-variant dark (&:is(.dark *))` — basta togglar
 * a classe `dark` no <html> raiz pra todas as vars CSS mudarem.
 */

import { useEffect, useMemo, useState } from "react";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "eskuta.theme";

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") {
    return stored;
  }
  return "system";
}

function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  const resolved = resolveTheme(theme);
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

export function useTheme(): {
  theme: Theme;
  resolved: "light" | "dark";
  setTheme: (next: Theme) => void;
} {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);
  // Tick incrementa quando o system theme muda — força re-resolução
  const [systemTick, setSystemTick] = useState(0);

  // Aplica classe DOM + resolve. useMemo evita o set-state-in-effect.
  const resolved = useMemo<"light" | "dark">(() => {
    const r = resolveTheme(theme);
    applyTheme(theme);
    return r;
    // systemTick é dependência intencional pra re-resolver quando OS
    // muda o preferred color scheme.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme, systemTick]);

  // Escuta mudança do system theme (apenas em modo system)
  useEffect(() => {
    if (theme !== "system" || typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemTick((t) => t + 1);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = (next: Theme) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
    setThemeState(next);
  };

  return { theme, resolved, setTheme };
}

/**
 * Aplica o tema salvo no primeiro paint — chamar antes do React montar
 * pra evitar FOUC (flash of wrong theme).
 */
export function initThemeFromStorage(): void {
  applyTheme(readStoredTheme());
}
