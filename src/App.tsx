import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError, waitForSidecar, type HealthResponse } from "@/lib/api";

type SidecarStatus =
  | { kind: "starting" }
  | { kind: "ready"; health: HealthResponse }
  | { kind: "failed"; error: string };

function App() {
  const [greetMsg, setGreetMsg] = useState("");
  const [name, setName] = useState("");
  const [sidecar, setSidecar] = useState<SidecarStatus>({ kind: "starting" });

  useEffect(() => {
    const abort = new AbortController();
    waitForSidecar({ signal: abort.signal })
      .then((health) => setSidecar({ kind: "ready", health }))
      .catch((err: unknown) => {
        const msg =
          err instanceof ApiError
            ? `${err.status} ${err.message}`
            : err instanceof Error
              ? err.message
              : String(err);
        setSidecar({ kind: "failed", error: msg });
      });
    return () => abort.abort();
  }, []);

  async function greet() {
    setGreetMsg(await invoke("greet", { name }));
  }

  return (
    <main className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-6 rounded-2xl border bg-card text-card-foreground p-8 shadow-sm">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">Eskuta</h1>
          <p className="text-sm text-muted-foreground">
            App desktop de transcrição e geração de atas de reunião — Fase 0
            (setup).
          </p>
        </header>

        <SidecarBadge status={sidecar} />

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            greet();
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder="Diga seu nome…"
            className={cn(
              "flex-1 rounded-md border bg-transparent px-3 py-2 text-sm",
              "placeholder:text-muted-foreground",
              "focus:outline-none focus:ring-2 focus:ring-ring",
            )}
          />
          <Button type="submit">Saudar</Button>
        </form>

        {greetMsg && (
          <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            {greetMsg}
          </p>
        )}
      </div>
    </main>
  );
}

function SidecarBadge({ status }: { status: SidecarStatus }) {
  const base =
    "rounded-md px-3 py-2 text-xs font-medium flex items-center gap-2";
  if (status.kind === "starting") {
    return (
      <div className={cn(base, "bg-muted text-muted-foreground")}>
        <span className="size-2 rounded-full bg-amber-500 animate-pulse" />
        Aguardando sidecar Python subir…
      </div>
    );
  }
  if (status.kind === "failed") {
    return (
      <div
        className={cn(
          base,
          "bg-destructive/10 text-destructive border border-destructive/20",
        )}
      >
        <span className="size-2 rounded-full bg-destructive" />
        Sidecar falhou: {status.error}
      </div>
    );
  }
  return (
    <div className={cn(base, "bg-emerald-500/10 text-emerald-700")}>
      <span className="size-2 rounded-full bg-emerald-500" />
      Sidecar OK · v{status.health.version}
    </div>
  );
}

export default App;
