/**
 * Toggle de tema light/dark/system. Botão único que cicla entre os 3.
 */

import { useTheme } from "@/lib/theme";

const NEXT: Record<"light" | "dark" | "system", "light" | "dark" | "system"> = {
  light: "dark",
  dark: "system",
  system: "light",
};

const ICON: Record<"light" | "dark" | "system", string> = {
  light: "☀",
  dark: "🌙",
  system: "🖥",
};

const LABEL: Record<"light" | "dark" | "system", string> = {
  light: "Tema: claro",
  dark: "Tema: escuro",
  system: "Tema: automático",
};

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={() => setTheme(NEXT[theme])}
      title={LABEL[theme] + " (clique pra alternar)"}
      aria-label={LABEL[theme]}
      className="inline-flex items-center gap-1.5 rounded-md border bg-transparent px-2 py-1 text-xs hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring"
    >
      <span aria-hidden="true">{ICON[theme]}</span>
      {!compact && (
        <span>
          {theme === "system" ? "Auto" : theme === "dark" ? "Escuro" : "Claro"}
        </span>
      )}
    </button>
  );
}
