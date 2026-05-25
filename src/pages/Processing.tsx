/**
 * Tela de processamento — polling do status até completed/failed.
 * Usa `pipelineProgress` (Bloco B.1) pra renderizar fase + ETA.
 */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import {
  PIPELINE_PHASES,
  type PipelineState,
  deriveState,
  formatEta,
} from "@/lib/pipelineProgress";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MeetingStatusResponse } from "@/types/meeting";

// Polling com backoff exponencial — minimiza load no sidecar pra reuniões
// longas. Começa em 1s e sobe até 8s, com jitter pra evitar thundering herd.
const POLL_BASE_MS = 1000;
const POLL_MAX_MS = 8000;
const POLL_GROWTH = 1.5;

function nextPollInterval(attempt: number): number {
  const exp = Math.min(
    POLL_MAX_MS,
    POLL_BASE_MS * Math.pow(POLL_GROWTH, attempt),
  );
  // Jitter ±15% pra dispersar requisições
  const jitter = exp * (Math.random() * 0.3 - 0.15);
  return Math.round(exp + jitter);
}

export function ProcessingPage() {
  const params = useParams<{ id: string }>();
  const meetingId = params.id!;
  const navigate = useNavigate();
  const [startedAt] = useState<number>(() => Date.now());
  const [status, setStatus] = useState<MeetingStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const tick = async () => {
      try {
        const next = await api.meetings.status(meetingId);
        if (cancelled) return;
        setStatus(next);
        if (next.status === "completed") {
          // Pequena pausa pra usuário ver "Pronto" antes do redirect
          timeout = setTimeout(() => navigate(`/meetings/${meetingId}`), 600);
          return;
        }
        if (next.status === "failed") {
          return; // não continua polling
        }
        // Backoff exponencial — menos load no sidecar pra reuniões longas
        timeout = setTimeout(tick, nextPollInterval(attempt));
        attempt += 1;
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? (err.detail ?? err.message)
            : err instanceof Error
              ? err.message
              : String(err);
        setError(msg);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timeout) clearTimeout(timeout);
    };
  }, [meetingId, navigate]);

  if (error !== null) {
    return (
      <div className="p-8">
        <h2 className="text-2xl font-semibold tracking-tight">Erro</h2>
        <p className="mt-2 text-sm text-destructive">{error}</p>
        <Link to="/" className="mt-4 inline-block">
          <Button variant="outline">Voltar pra lista</Button>
        </Link>
      </div>
    );
  }

  if (status === null) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">Conectando…</p>
      </div>
    );
  }

  const state = deriveState(status.status, status.error, startedAt);

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-2xl font-semibold tracking-tight">
        {state.kind === "failed"
          ? "Falhou"
          : state.kind === "completed"
            ? "Pronto"
            : "Processando…"}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        ID: <code className="font-mono text-xs">{meetingId}</code>
      </p>

      <div className="mt-8">
        <ProgressView state={state} />
      </div>

      {state.kind === "failed" && (
        <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-sm font-medium text-destructive">
            {state.errorMessage ?? "Erro desconhecido no pipeline."}
          </p>
          <Link to="/" className="mt-3 inline-block">
            <Button variant="outline" size="sm">
              Voltar pra lista
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

function ProgressView({ state }: { state: PipelineState }) {
  if (state.kind === "failed") {
    return <FailedTimeline />;
  }
  if (state.kind === "completed") {
    return (
      <div className="rounded-md border bg-emerald-500/5 p-4 text-sm text-emerald-700">
        Tudo pronto. Redirecionando pra ata…
      </div>
    );
  }
  const { currentPhase, progressPercent, etaSecondsRemaining } = state;
  return (
    <>
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">{currentPhase.label}</span>
        <span className="text-muted-foreground">
          {progressPercent}% · resta {formatEta(etaSecondsRemaining)}
        </span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-[width] duration-500"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
      <ol className="mt-6 space-y-2">
        {PIPELINE_PHASES.filter((p) => p.status !== "completed").map(
          (phase) => {
            const done = phase.position < currentPhase.position;
            const active = phase.position === currentPhase.position;
            return (
              <li
                key={phase.status}
                className={cn(
                  "flex items-center gap-3 text-sm",
                  done
                    ? "text-muted-foreground line-through"
                    : active
                      ? "text-foreground font-medium"
                      : "text-muted-foreground/70",
                )}
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    done
                      ? "bg-emerald-500"
                      : active
                        ? "bg-amber-500 animate-pulse"
                        : "bg-muted-foreground/30",
                  )}
                />
                {phase.label}
              </li>
            );
          },
        )}
      </ol>
    </>
  );
}

function FailedTimeline() {
  return (
    <ol className="space-y-2">
      {PIPELINE_PHASES.filter((p) => p.status !== "completed").map((phase) => (
        <li
          key={phase.status}
          className="flex items-center gap-3 text-sm text-muted-foreground/60"
        >
          <span className="size-2 rounded-full bg-muted-foreground/30" />
          {phase.label}
        </li>
      ))}
    </ol>
  );
}
