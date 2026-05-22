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
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import { UpdateChecker } from "@/components/UpdateChecker";
import { Button } from "@/components/ui/button";
import { ApiError, type HealthResponse, waitForSidecar } from "@/lib/api";
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

function SidecarGate({
  status,
}: {
  status: { kind: "starting" } | { kind: "failed"; error: string };
}) {
  const base =
    "min-h-screen flex items-center justify-center p-6 bg-background";
  if (status.kind === "starting") {
    return (
      <div className={base}>
        <div className="text-center space-y-3">
          <div className="size-3 mx-auto rounded-full bg-amber-500 animate-pulse" />
          <p className="text-sm text-muted-foreground">
            Aguardando sidecar Python subir…
          </p>
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
          Sidecar não respondeu
        </h2>
        <p className="mt-2 text-sm text-destructive/80">{status.error}</p>
        <p className="mt-3 text-xs text-muted-foreground">
          Verifique os logs em ~/.eskuta/logs/ ou reinicie o app.
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
