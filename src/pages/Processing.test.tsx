import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    status: number;
    body: unknown;
    detail: string | null;
    constructor(status: number, body: unknown, message?: string) {
      super(message ?? `Sidecar respondeu ${status}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: string }).detail
          : null;
    }
  }
  return {
    status: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: { meetings: { status: apiMocks.status } },
  ApiError: apiMocks.ApiError,
}));

const ApiErrorMock = apiMocks.ApiError;

import { ProcessingPage } from "./Processing";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/processing/m1"]}>
      <Routes>
        <Route path="/processing/:id" element={<ProcessingPage />} />
        <Route path="/" element={<p>home landed</p>} />
        <Route path="/meetings/:id" element={<p>meeting landed</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMocks.status.mockReset();
});

describe("ProcessingPage", () => {
  it("mostra 'Conectando…' antes do primeiro poll responder", () => {
    apiMocks.status.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/conectando/i)).toBeInTheDocument();
  });

  it("renderiza progresso quando status=transcribing", async () => {
    apiMocks.status.mockResolvedValue({
      id: "m1",
      status: "transcribing",
      error: null,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/processando/i)).toBeInTheDocument();
    });
    // ID exibido
    expect(screen.getByText(/m1/)).toBeInTheDocument();
    // Algum % na UI de progresso
    expect(screen.getByText(/resta/i)).toBeInTheDocument();
  });

  it("renderiza 'Pronto' quando status=completed (e schedula navigate)", async () => {
    apiMocks.status.mockResolvedValue({
      id: "m1",
      status: "completed",
      error: null,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^pronto$/i)).toBeInTheDocument();
    });
    // Mensagem de "Redirecionando" aparece — o timeout de 600ms pra navigate
    // não precisa ser exercitado (cleanup do useEffect cancela quando o test desmonta).
    expect(screen.getByText(/redirecionando/i)).toBeInTheDocument();
  });

  it("navega pra /meetings/:id após status=completed (timer real)", async () => {
    apiMocks.status.mockResolvedValue({
      id: "m1",
      status: "completed",
      error: null,
    });
    renderPage();
    await waitFor(
      () => {
        expect(screen.getByText(/meeting landed/i)).toBeInTheDocument();
      },
      { timeout: 2500 },
    );
  });

  it("renderiza 'Falhou' + mensagem quando status=failed com error", async () => {
    apiMocks.status.mockResolvedValue({
      id: "m1",
      status: "failed",
      error: "transcrição quebrou",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^falhou$/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/transcrição quebrou/i)).toBeInTheDocument();
    // Botão 'Voltar pra lista' aparece no banner de erro
    expect(
      screen.getByRole("button", { name: /voltar pra lista/i }),
    ).toBeInTheDocument();
  });

  it("usa fallback 'Erro desconhecido' quando failed sem error message", async () => {
    apiMocks.status.mockResolvedValue({
      id: "m1",
      status: "failed",
      error: null,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/erro desconhecido/i)).toBeInTheDocument();
    });
  });

  it("mostra UI de erro quando api.status rejeita com Error", async () => {
    apiMocks.status.mockRejectedValue(new Error("connection refused"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^erro$/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/connection refused/i)).toBeInTheDocument();
  });

  it("mostra detail quando api.status rejeita com ApiError", async () => {
    apiMocks.status.mockRejectedValue(
      new ApiErrorMock(500, { detail: "boom interno" }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/boom interno/i)).toBeInTheDocument();
    });
  });

  it("rejeição com não-Error usa String(err)", async () => {
    apiMocks.status.mockRejectedValue("plain string err");
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/plain string err/i)).toBeInTheDocument();
    });
  });
});
