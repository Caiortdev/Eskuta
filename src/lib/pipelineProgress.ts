/**
 * Pipeline progress — lógica pura pra mapear o `meeting.status` do
 * backend em algo renderizável (label, fase number, percent, ETA).
 *
 * Implementa o **Bloco B.1** de `docs/MELHORIAS-CONCORRENTE.md` —
 * inspirado no `pipelineProgress.ts` do concorrente, mas adaptado ao
 * nosso schema (8 estágios + failed) e em pt-BR. Lógica pura, sem
 * dependências de React; testável isoladamente via vitest.
 */

import type { MeetingStatus } from "@/types/meeting";

export interface PipelinePhase {
  status: MeetingStatus;
  label: string;
  /** 1-indexado pra display (1 de N) */
  position: number;
}

/**
 * Ordem canônica das fases. NÃO inclui `failed` — é estado terminal
 * fora da progressão linear.
 */
export const PIPELINE_PHASES: readonly PipelinePhase[] = [
  { status: "pending", label: "Na fila", position: 1 },
  { status: "converting", label: "Preparando áudio", position: 2 },
  { status: "detecting_speech", label: "Detectando fala", position: 3 },
  { status: "chunking", label: "Dividindo em blocos", position: 4 },
  { status: "transcribing", label: "Transcrevendo", position: 5 },
  { status: "diarizing", label: "Identificando speakers", position: 6 },
  { status: "generating_minutes", label: "Gerando ata", position: 7 },
  { status: "validating", label: "Validando", position: 8 },
  { status: "completed", label: "Pronto", position: 9 },
] as const;

const PHASE_BY_STATUS = new Map<MeetingStatus, PipelinePhase>(
  PIPELINE_PHASES.map((p) => [p.status, p]),
);

export const TOTAL_PHASES = PIPELINE_PHASES.length - 1; // exclui "completed" do contador

export type PipelineState =
  | {
      kind: "running";
      currentPhase: PipelinePhase;
      progressPercent: number;
      etaSecondsRemaining: number | null;
    }
  | { kind: "completed"; finishedAt: number }
  | { kind: "failed"; errorMessage: string | null };

/**
 * Dado o status atual, retorna a fase canônica.
 *
 * Status desconhecidos (defensivo — backend pode adicionar novos) caem
 * num phase placeholder com label genérico.
 */
export function phaseFromStatus(status: MeetingStatus): PipelinePhase {
  const known = PHASE_BY_STATUS.get(status);
  if (known) return known;
  // Defensivo: deveria ser inalcançável dado o tipo MeetingStatus
  return { status, label: status, position: 0 };
}

/**
 * Calcula percentual de progresso linear (1ª fase = 0%, última antes
 * de completed = ~100%). Útil pra progress bar.
 */
export function progressPercent(status: MeetingStatus): number {
  const phase = phaseFromStatus(status);
  if (phase.status === "completed") return 100;
  if (phase.position === 0) return 0;
  // Phases "pending" (1) … "validating" (8) → 0%-87.5%; completed → 100
  return Math.round((phase.position - 1) * (100 / TOTAL_PHASES));
}

/**
 * Modela o estado do pipeline a partir do polling do backend.
 *
 * @param status status atual da meeting
 * @param error mensagem de erro se `status="failed"`
 * @param startedAtMs timestamp em ms (Date.now()) de quando começou a observação;
 *                    usado pra calcular ETA
 * @param nowMs timestamp atual (default: Date.now()) — injectable pra testes
 */
export function deriveState(
  status: MeetingStatus,
  error: string | null,
  startedAtMs: number | null,
  nowMs: number = Date.now(),
): PipelineState {
  if (status === "failed") {
    return { kind: "failed", errorMessage: error };
  }
  if (status === "completed") {
    return { kind: "completed", finishedAt: nowMs };
  }
  return {
    kind: "running",
    currentPhase: phaseFromStatus(status),
    progressPercent: progressPercent(status),
    etaSecondsRemaining: estimateEta(status, startedAtMs, nowMs),
  };
}

/**
 * Estima quantos segundos faltam.
 *
 * Heurística simples: se passou `elapsed` segundos e estamos em `p%`,
 * estimamos total = elapsed / (p / 100) e ETA = total - elapsed.
 *
 * Retorna `null` se p é 0 (não dá pra estimar ainda) ou startedAtMs
 * inválido. ETA negativo é clampado em 0.
 */
export function estimateEta(
  status: MeetingStatus,
  startedAtMs: number | null,
  nowMs: number,
): number | null {
  if (startedAtMs === null || startedAtMs <= 0 || nowMs <= startedAtMs) {
    return null;
  }
  const percent = progressPercent(status);
  if (percent <= 0) {
    return null;
  }
  const elapsedSec = (nowMs - startedAtMs) / 1000;
  const estimatedTotal = elapsedSec / (percent / 100);
  const remaining = estimatedTotal - elapsedSec;
  if (!Number.isFinite(remaining)) {
    return null;
  }
  return Math.max(0, Math.round(remaining));
}

/**
 * Formata segundos em "Xm Ys" ou "Ys" pt-BR pra exibir ao usuário.
 */
export function formatEta(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (remaining === 0) return `${minutes}min`;
  return `${minutes}min ${remaining}s`;
}
