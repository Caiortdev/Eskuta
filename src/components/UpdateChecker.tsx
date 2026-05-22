/**
 * UpdateChecker — checa updates do app via tauri-plugin-updater no startup.
 *
 * Comportamento:
 * - Roda só em ambiente Tauri (detecta via window.__TAURI_INTERNALS__)
 * - Checa update na montagem (1x)
 * - Se houver update e o usuário aceitar, baixa e instala
 * - Se update não tá disponível ou plugin não habilitado, silenciosamente
 *   não renderiza nada (não atrapalha quem roda em dev/browser)
 *
 * Configurado pra rodar somente quando `plugins.updater.active=true` no
 * tauri.conf.json. Por default o updater fica desabilitado até que o
 * endpoint real + pubkey estejam configurados.
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type UpdateState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "available"; version: string; body: string | null }
  | { kind: "downloading"; progress: number }
  | { kind: "installed" }
  | { kind: "error"; message: string };

function isTauriEnv(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as unknown as Record<string, unknown>)
  );
}

export function UpdateChecker() {
  // Lazy init: começa em "checking" se rodando em Tauri, "idle" caso contrário
  // (evita o lint react-hooks/set-state-in-effect)
  const [state, setState] = useState<UpdateState>(() =>
    isTauriEnv() ? { kind: "checking" } : { kind: "idle" },
  );
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!isTauriEnv()) return;
    let cancelled = false;

    void (async () => {
      try {
        // Import dinâmico — evita carregar o plugin em ambientes não-Tauri (dev/test)
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (cancelled) return;
        if (!update) {
          setState({ kind: "idle" });
          return;
        }
        setState({
          kind: "available",
          version: update.version,
          body: update.body ?? null,
        });
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        // Se o updater não tá habilitado, dá erro mas a gente silencia
        // (não vamos mostrar UI de erro de update na cara do usuário)
        if (
          msg.toLowerCase().includes("not enabled") ||
          msg.toLowerCase().includes("disabled")
        ) {
          setState({ kind: "idle" });
          return;
        }
        setState({ kind: "error", message: msg });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const installUpdate = async () => {
    if (state.kind !== "available") return;
    setState({ kind: "downloading", progress: 0 });
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) {
        setState({ kind: "idle" });
        return;
      }
      let downloaded = 0;
      let total = 0;
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") {
          total = event.data.contentLength ?? 0;
        } else if (event.event === "Progress") {
          downloaded += event.data.chunkLength;
          const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
          setState({ kind: "downloading", progress: pct });
        }
      });
      setState({ kind: "installed" });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  };

  // Estados que não merecem UI visível
  if (dismissed) return null;
  if (state.kind === "idle" || state.kind === "checking") return null;
  if (state.kind === "error") return null; // erros de update não atrapalham UX

  return (
    <div
      role="dialog"
      aria-label="Atualização disponível"
      className="fixed bottom-4 right-4 z-40 max-w-sm rounded-lg border bg-background p-4 shadow-lg"
    >
      {state.kind === "available" && (
        <>
          <p className="text-sm font-medium">
            Nova versão disponível ({state.version})
          </p>
          {state.body && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-3">
              {state.body}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button type="button" size="sm" onClick={installUpdate}>
              Instalar agora
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setDismissed(true)}
            >
              Depois
            </Button>
          </div>
        </>
      )}
      {state.kind === "downloading" && (
        <>
          <p className="text-sm font-medium">Baixando atualização…</p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-[width]"
              style={{ width: `${state.progress}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {state.progress}%
          </p>
        </>
      )}
      {state.kind === "installed" && (
        <>
          <p className="text-sm font-medium">✓ Atualização instalada</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Reinicie o app pra aplicar.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="mt-3"
            onClick={() => setDismissed(true)}
          >
            Ok
          </Button>
        </>
      )}
    </div>
  );
}
