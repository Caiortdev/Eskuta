/**
 * Tests do pipelineProgress (Bloco B.1).
 * Lógica pura — sem mocks, sem React.
 */

import { describe, expect, it } from "vitest";
import {
  PIPELINE_PHASES,
  TOTAL_PHASES,
  deriveState,
  estimateEta,
  formatEta,
  phaseFromStatus,
  progressPercent,
} from "@/lib/pipelineProgress";
import type { MeetingStatus } from "@/types/meeting";

describe("PIPELINE_PHASES — constantes", () => {
  it("inclui 9 fases (pending → completed)", () => {
    expect(PIPELINE_PHASES.length).toBe(9);
  });

  it("primeira fase é pending, última é completed", () => {
    expect(PIPELINE_PHASES[0].status).toBe("pending");
    expect(PIPELINE_PHASES[PIPELINE_PHASES.length - 1].status).toBe(
      "completed",
    );
  });

  it("TOTAL_PHASES exclui completed (8 fases ativas)", () => {
    expect(TOTAL_PHASES).toBe(8);
  });

  it("positions são 1-indexadas e sequenciais", () => {
    PIPELINE_PHASES.forEach((p, i) => {
      expect(p.position).toBe(i + 1);
    });
  });
});

describe("phaseFromStatus", () => {
  it("retorna a fase canônica pra cada status conhecido", () => {
    expect(phaseFromStatus("pending").label).toBe("Na fila");
    expect(phaseFromStatus("transcribing").label).toBe("Transcrevendo");
    expect(phaseFromStatus("completed").label).toBe("Pronto");
  });

  it("usa position correta", () => {
    expect(phaseFromStatus("pending").position).toBe(1);
    expect(phaseFromStatus("converting").position).toBe(2);
    expect(phaseFromStatus("validating").position).toBe(8);
    expect(phaseFromStatus("completed").position).toBe(9);
  });
});

describe("progressPercent", () => {
  it("pending = 0%", () => {
    expect(progressPercent("pending")).toBe(0);
  });

  it("completed = 100%", () => {
    expect(progressPercent("completed")).toBe(100);
  });

  it("validating = ~87.5% (7/8)", () => {
    expect(progressPercent("validating")).toBe(88);
  });

  it("transcribing = 50% (4/8)", () => {
    expect(progressPercent("transcribing")).toBe(50);
  });
});

describe("deriveState", () => {
  it("status 'completed' → kind=completed", () => {
    const state = deriveState("completed", null, 1000, 2000);
    expect(state.kind).toBe("completed");
  });

  it("status 'failed' → kind=failed com error", () => {
    const state = deriveState("failed", "boom", 1000, 2000);
    expect(state.kind).toBe("failed");
    if (state.kind === "failed") {
      expect(state.errorMessage).toBe("boom");
    }
  });

  it("status running → currentPhase + progressPercent + eta", () => {
    const state = deriveState("transcribing", null, 1000, 11000); // 10s passados, em 50%
    expect(state.kind).toBe("running");
    if (state.kind === "running") {
      expect(state.currentPhase.status).toBe("transcribing");
      expect(state.progressPercent).toBe(50);
      // 10s passados em 50% → estimativa total = 20s → resta 10s
      expect(state.etaSecondsRemaining).toBe(10);
    }
  });

  it("status failed sem error message vira null", () => {
    const state = deriveState("failed", null, 1000, 2000);
    if (state.kind === "failed") {
      expect(state.errorMessage).toBeNull();
    }
  });
});

describe("estimateEta", () => {
  it("retorna null se startedAtMs é null", () => {
    expect(estimateEta("transcribing", null, 1000)).toBeNull();
  });

  it("retorna null se nowMs <= startedAtMs", () => {
    expect(estimateEta("transcribing", 5000, 4000)).toBeNull();
    expect(estimateEta("transcribing", 5000, 5000)).toBeNull();
  });

  it("retorna null em fases com 0% (pending)", () => {
    expect(estimateEta("pending", 1000, 11000)).toBeNull();
  });

  it("calcula ETA simétrico: 10s em 50% → 10s restantes", () => {
    expect(estimateEta("transcribing", 1000, 11000)).toBe(10);
  });

  it("clampa ETA negativo em 0", () => {
    // Cenário improvável: muitíssimo tempo passado em fase baixa
    const result = estimateEta("converting", 1000, 60000);
    expect(result).toBeGreaterThanOrEqual(0);
  });
});

describe("formatEta", () => {
  it("null → '—'", () => {
    expect(formatEta(null)).toBe("—");
  });

  it("segundos abaixo de 60 → 'Xs'", () => {
    expect(formatEta(42)).toBe("42s");
  });

  it("minuto exato → 'Xmin'", () => {
    expect(formatEta(120)).toBe("2min");
  });

  it("min + sec → 'Xmin Ys'", () => {
    expect(formatEta(125)).toBe("2min 5s");
  });
});

describe("status defensivo desconhecido", () => {
  it("status fora do enum vira fase com position=0 + label=status", () => {
    const phase = phaseFromStatus("xxx" as MeetingStatus);
    expect(phase.position).toBe(0);
    expect(phase.label).toBe("xxx");
  });

  it("progressPercent com status desconhecido = 0%", () => {
    expect(progressPercent("xxx" as MeetingStatus)).toBe(0);
  });
});
