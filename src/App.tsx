/**
 * Root da SPA. Faz duas coisas:
 *
 * 1. Espera o sidecar Python subir (waitForSidecar) — bloqueia toda a UI
 *    até /health responder. Sem isso, qualquer chamada quebra.
 * 2. Monta o React Router com layout principal + rotas.
 *
 * Onboarding fica fora do AppLayout (sem sidebar) — é o gate inicial.
 */

import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { UpdateChecker } from "@/components/UpdateChecker";
import { Button } from "@/components/ui/button";
import { ApiError, type HealthResponse, waitForSidecar } from "@/lib/api";
import { useShortcuts } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { HomePage } from "@/pages/Home";
import { MeetingDetailPage } from "@/pages/MeetingDetail";
import { OnboardingPage } from "@/pages/Onboarding";
import { ProcessingPage } from "@/pages/Processing";
import { SettingsPage } from "@/pages/Settings";
import { UploadPage } from "@/pages/Upload";

type SidecarStatus =
  | { kind: "starting" }
  | { kind: "ready"; health: HealthResponse }
  | { kind: "failed"; error: string };

function App() {
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

  if (sidecar.kind !== "ready") {
    return <SidecarGate status={sidecar} />;
  }

  return (
    <BrowserRouter>
      <UpdateChecker />
      <ShortcutsHost />
      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/processing/:id" element={<ProcessingPage />} />
          <Route path="/meetings/:id" element={<MeetingDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

function ShortcutsHost() {
  const navigate = useNavigate();
  useShortcuts([
    {
      key: "u",
      mod: true,
      description: "Ir pra Nova reunião",
      handler: (e) => {
        e.preventDefault();
        navigate("/upload");
      },
    },
    {
      key: ",",
      mod: true,
      description: "Abrir Configurações",
      handler: (e) => {
        e.preventDefault();
        navigate("/settings");
      },
    },
    {
      key: "h",
      mod: true,
      description: "Ir pra Início (Reuniões)",
      handler: (e) => {
        e.preventDefault();
        navigate("/");
      },
    },
  ]);
  return null;
}

function SidecarGate({
  status,
}: {
  status: { kind: "starting" } | { kind: "failed"; error: string };
}) {
  const base =
    "min-h-screen flex items-center justify-center p-6 bg-background";

  // Mostra mensagem progressiva — a primeira frase aparece imediato (sem
  // delay), as outras só se a inicialização demorar muito.
  const [secondsElapsed, setSecondsElapsed] = useState(0);
  useEffect(() => {
    if (status.kind !== "starting") return;
    const t = setInterval(() => setSecondsElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [status.kind]);

  if (status.kind === "starting") {
    return (
      <div className={base}>
        <div className="text-center space-y-6 max-w-sm">
          {/* Logo + spinner */}
          <div className="flex flex-col items-center gap-4">
            <div className="size-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <span className="text-3xl">🎙️</span>
            </div>
            <div className="flex gap-1">
              <div className="size-2 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]" />
              <div className="size-2 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]" />
              <div className="size-2 rounded-full bg-primary animate-bounce" />
            </div>
          </div>
          <div className="space-y-2">
            <h1 className="text-xl font-semibold tracking-tight">Eskuta</h1>
            <p className="text-sm text-muted-foreground">
              {secondsElapsed < 4
                ? "Iniciando…"
                : secondsElapsed < 10
                  ? "Preparando o motor de transcrição…"
                  : "Quase lá, aguentando aí…"}
            </p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className={base}>
      <div
        className={cn(
          "max-w-md rounded-md border border-destructive/30 bg-destructive/5",
          "p-6 text-center",
        )}
      >
        <h2 className="text-lg font-semibold text-destructive">
          Não consegui iniciar o Eskuta
        </h2>
        <p className="mt-2 text-sm text-destructive/80">{status.error}</p>
        <p className="mt-3 text-xs text-muted-foreground">
          Se o problema persistir, em{" "}
          <strong>Configurações &gt; Diagnóstico</strong> exporte os logs e
          envie pro suporte.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => window.location.reload()}
        >
          Tentar de novo
        </Button>
      </div>
    </div>
  );
}

export default App;
