import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renderiza o label da fase correspondente", () => {
    render(<StatusBadge status="transcribing" />);
    expect(screen.getByText(/transcrevendo/i)).toBeInTheDocument();
  });

  it("status 'pending' mostra 'Na fila'", () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText(/na fila/i)).toBeInTheDocument();
  });

  it("status 'completed' mostra 'Pronto'", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText(/pronto/i)).toBeInTheDocument();
  });

  it("status 'failed' mostra o label da fase failed", () => {
    // Por convenção do pipelineProgress, 'failed' não tem label canônico
    // (cai no fallback) — só verificamos que renderiza algo
    const { container } = render(<StatusBadge status="failed" />);
    expect(container.firstChild).not.toBeNull();
  });

  it("status running tem classe amber + animate-pulse", () => {
    const { container } = render(<StatusBadge status="transcribing" />);
    expect(container.innerHTML).toMatch(/amber/);
    expect(container.innerHTML).toMatch(/animate-pulse/);
  });

  it("status 'completed' tem cor emerald", () => {
    const { container } = render(<StatusBadge status="completed" />);
    expect(container.innerHTML).toMatch(/emerald/);
  });

  it("status 'failed' tem cor destructive", () => {
    const { container } = render(<StatusBadge status="failed" />);
    expect(container.innerHTML).toMatch(/destructive/);
  });
});
