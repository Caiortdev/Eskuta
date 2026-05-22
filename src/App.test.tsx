/**
 * Testes do gate de sidecar do App.tsx — os tests das páginas
 * individuais ficam em src/pages/__tests__/* (não escopo aqui).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock controlado do api.ts — vi.mock() é hoisted, por isso usamos
// hoisted state via vi.hoisted() pra referenciar o mock nas asserções.
const apiMocks = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    status: number;
    body: unknown;
    constructor(status: number, body: unknown, message?: string) {
      super(message ?? `Sidecar respondeu ${status}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
    }
  }
  return {
    waitForSidecar: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  ApiError: apiMocks.ApiError,
  waitForSidecar: apiMocks.waitForSidecar,
  api: {
    meetings: { list: vi.fn().mockResolvedValue({ meetings: [], total: 0 }) },
    keys: { list: vi.fn().mockResolvedValue({ providers: [] }) },
  },
}));

import App from "./App";

const { waitForSidecar: waitForSidecarMock, ApiError: ApiErrorMock } = apiMocks;

beforeEach(() => {
  waitForSidecarMock.mockReset();
});

describe("App — gate de sidecar", () => {
  it("mostra 'Aguardando sidecar' enquanto health não responde", () => {
    waitForSidecarMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<App />);
    expect(screen.getByText(/aguardando sidecar/i)).toBeInTheDocument();
  });

  it("mostra mensagem de erro quando waitForSidecar rejeita com Error", async () => {
    waitForSidecarMock.mockRejectedValue(new Error("connection refused"));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar não respondeu/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/connection refused/i)).toBeInTheDocument();
  });

  it("mostra status code quando waitForSidecar rejeita com ApiError", async () => {
    waitForSidecarMock.mockRejectedValue(
      new ApiErrorMock(503, { detail: "down" }),
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar não respondeu/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/503/)).toBeInTheDocument();
  });

  it("renderiza app principal (sidebar 'Reuniões') quando sidecar fica pronto", async () => {
    waitForSidecarMock.mockResolvedValue({ status: "ok", version: "0.1.0" });
    render(<App />);
    await waitFor(() => {
      // Sidebar do AppLayout tem link "Reuniões"
      expect(screen.getAllByText(/reuniões/i).length).toBeGreaterThan(0);
    });
  });

  it("botão 'Tentar de novo' aparece em estado de falha", async () => {
    waitForSidecarMock.mockRejectedValue(new Error("boom"));
    render(<App />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /tentar de novo/i }),
      ).toBeInTheDocument();
    });
  });
});
