/**
 * Keyboard shortcuts globais do app.
 *
 * Estilo VS Code / GitHub Desktop — Ctrl+ atalhos pra ações de página
 * principal, sem atrapalhar input fields (não dispara se o usuário tá
 * digitando em input/textarea/contenteditable).
 */

import { useEffect } from "react";

export interface Shortcut {
  /** Caractere ou nome de tecla (ex: "u", ",", "/") */
  key: string;
  /** Requer Ctrl (Win/Linux) ou Cmd (Mac) — controla com isMod */
  mod?: boolean;
  /** Requer Shift */
  shift?: boolean;
  /** Requer Alt */
  alt?: boolean;
  /** Descrição pra UI/help */
  description: string;
  /** Handler — recebe evento pra opcionalmente preventDefault */
  handler: (e: KeyboardEvent) => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function matches(event: KeyboardEvent, shortcut: Shortcut): boolean {
  if (shortcut.mod && !(event.ctrlKey || event.metaKey)) return false;
  if (!shortcut.mod && (event.ctrlKey || event.metaKey)) return false;
  if (shortcut.shift && !event.shiftKey) return false;
  if (!shortcut.shift && event.shiftKey) return false;
  if (shortcut.alt && !event.altKey) return false;
  if (!shortcut.alt && event.altKey) return false;
  return event.key.toLowerCase() === shortcut.key.toLowerCase();
}

/**
 * Registra um conjunto de atalhos globais enquanto o componente está montado.
 *
 * IMPORTANTE: passe a lista como estável (useMemo ou constante fora do
 * componente) pra evitar re-bind a cada render.
 */
export function useShortcuts(shortcuts: Shortcut[]): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      for (const sc of shortcuts) {
        if (matches(event, sc)) {
          sc.handler(event);
          return;
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts]);
}
