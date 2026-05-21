import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi
    .fn()
    .mockResolvedValue("Hello, Eskuta! You've been greeted from Rust!"),
}));

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
}));

import App from "./App";
import { invoke } from "@tauri-apps/api/core";

const { waitForSidecar: waitForSidecarMock, ApiError: ApiErrorMock } = apiMocks;

beforeEach(() => {
  waitForSidecarMock.mockReset();
  vi.mocked(invoke).mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("App — render base", () => {
  it("renderiza título Eskuta", () => {
    waitForSidecarMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /eskuta/i, level: 1 }),
    ).toBeInTheDocument();
  });
});

describe("App — estados do sidecar", () => {
  it("mostra 'Aguardando sidecar' enquanto health não responde", () => {
    waitForSidecarMock.mockReturnValue(new Promise(() => {}));
    render(<App />);
    expect(screen.getByText(/aguardando sidecar/i)).toBeInTheDocument();
  });

  it("mostra 'Sidecar OK · v{version}' quando waitForSidecar resolve", async () => {
    waitForSidecarMock.mockResolvedValue({ status: "ok", version: "0.1.0" });
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar ok/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/v0\.1\.0/)).toBeInTheDocument();
  });

  it("mostra badge de falha com mensagem quando waitForSidecar rejeita com Error", async () => {
    waitForSidecarMock.mockRejectedValue(new Error("connection refused"));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar falhou/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/connection refused/i)).toBeInTheDocument();
  });

  it("mostra badge de falha com status quando waitForSidecar rejeita com ApiError", async () => {
    waitForSidecarMock.mockRejectedValue(
      new ApiErrorMock(503, { detail: "down" }),
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar falhou/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/503/)).toBeInTheDocument();
  });

  it("mostra mensagem genérica quando waitForSidecar rejeita com valor não-Error", async () => {
    waitForSidecarMock.mockRejectedValue("kaboom");
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar falhou/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/kaboom/)).toBeInTheDocument();
  });
});

describe("App — interação greet", () => {
  it("invoca o comando Rust 'greet' ao submeter o form", async () => {
    waitForSidecarMock.mockResolvedValue({ status: "ok", version: "0.1.0" });
    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByPlaceholderText(/diga seu nome/i);
    await user.type(input, "Caio");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /saudar/i }));
    });

    expect(invoke).toHaveBeenCalledWith("greet", { name: "Caio" });
    await waitFor(() => {
      expect(
        screen.getByText(/hello, eskuta! you've been greeted from rust/i),
      ).toBeInTheDocument();
    });
  });
});
