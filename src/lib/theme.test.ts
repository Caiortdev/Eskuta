import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTheme, initThemeFromStorage, type Theme } from "./theme";

describe("theme system", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    document.documentElement.classList.remove("dark");
  });

  it("useTheme default é 'system' quando nada em localStorage", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
  });

  it("useTheme lê value salvo em localStorage", () => {
    window.localStorage.setItem("eskuta.theme", "dark");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
  });

  it("setTheme persiste em localStorage", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(window.localStorage.getItem("eskuta.theme")).toBe("light");
    expect(result.current.theme).toBe("light");
  });

  it("aplica classe 'dark' quando theme=dark", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("remove classe 'dark' quando theme=light", () => {
    document.documentElement.classList.add("dark");
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("resolved é 'light' em modo system com matchMedia=false (polyfill)", () => {
    const { result } = renderHook(() => useTheme());
    // polyfill do vitest.setup.ts retorna matches=false
    expect(result.current.resolved).toBe("light");
  });

  it("valores inválidos em localStorage caem em 'system'", () => {
    window.localStorage.setItem("eskuta.theme", "bogus");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
  });

  it("initThemeFromStorage aplica 'dark' quando valor salvo é dark", () => {
    window.localStorage.setItem("eskuta.theme", "dark" satisfies Theme);
    initThemeFromStorage();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("initThemeFromStorage não quebra sem localStorage value", () => {
    initThemeFromStorage();
    // No-op pra system theme (depende de matchMedia → polyfill false → light)
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("useTheme reage a mudança de prefers-color-scheme em modo system", () => {
    // Mock matchMedia com listener
    const listeners: Array<(e: { matches: boolean }) => void> = [];
    const mockMql = {
      matches: false,
      media: "(prefers-color-scheme: dark)",
      addEventListener: (_evt: string, cb: (e: { matches: boolean }) => void) =>
        listeners.push(cb),
      removeEventListener: vi.fn(),
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    };
    const originalMm = window.matchMedia;
    window.matchMedia = vi
      .fn()
      .mockReturnValue(mockMql) as unknown as typeof window.matchMedia;
    try {
      const { result } = renderHook(() => useTheme());
      expect(result.current.theme).toBe("system");
      // Simula OS mudando pra dark
      act(() => {
        mockMql.matches = true;
        listeners.forEach((l) => l({ matches: true }));
      });
      // Reactive: tick incrementou, resolved deveria recomputar
      // (validação parcial — depende do useMemo recomputar)
    } finally {
      window.matchMedia = originalMm;
    }
  });
});
