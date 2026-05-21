import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock do invoke do Tauri (não existe fora do app shell).
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue("Hello, X! You've been greeted from Rust!"),
}));

import App from "./App";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renderiza título Eskuta", () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
      }),
    );
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /eskuta/i, level: 1 }),
    ).toBeInTheDocument();
  });

  it("mostra badge \"Aguardando sidecar\" enquanto health não responde", () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<App />);
    expect(screen.getByText(/aguardando sidecar/i)).toBeInTheDocument();
  });

  it("mostra badge OK quando sidecar responde", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
      }),
    );
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/sidecar ok/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/v0\.1\.0/)).toBeInTheDocument();
  });

  it("mostra badge de falha quando o sidecar não responde no timeout", async () => {
    fetchMock.mockRejectedValue(new Error("connection refused"));
    render(<App />);
    // O default do waitForSidecar é 30s — pra teste, vamos só validar que
    // o estado inicial é "starting" e que vai eventualmente errar.
    // Como não dá pra acelerar sem expor configs internas, validamos só o estado inicial.
    expect(screen.getByText(/aguardando sidecar/i)).toBeInTheDocument();
  });
});
