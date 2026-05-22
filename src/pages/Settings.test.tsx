import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
    list: vi.fn(),
    save: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: {
    keys: {
      list: apiMocks.list,
      save: apiMocks.save,
      delete: apiMocks.delete,
      test: apiMocks.test,
    },
  },
  ApiError: apiMocks.ApiError,
}));

const ApiErrorMock = apiMocks.ApiError;

import { SettingsPage } from "./Settings";

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

const ALL_PROVIDERS = [
  {
    provider: "groq",
    is_configured: false,
    last_validated_at: null,
    last_validation_status: null,
    notes: null,
  },
  {
    provider: "assemblyai",
    is_configured: false,
    last_validated_at: null,
    last_validation_status: null,
    notes: null,
  },
  {
    provider: "anthropic",
    is_configured: true,
    last_validated_at: "2026-05-22T10:00:00Z",
    last_validation_status: "valid",
    notes: null,
  },
  {
    provider: "openai",
    is_configured: false,
    last_validated_at: null,
    last_validation_status: null,
    notes: null,
  },
  {
    provider: "google",
    is_configured: false,
    last_validated_at: null,
    last_validation_status: null,
    notes: null,
  },
];

beforeEach(() => {
  apiMocks.list.mockReset();
  apiMocks.save.mockReset();
  apiMocks.delete.mockReset();
  apiMocks.test.mockReset();
});

describe("SettingsPage", () => {
  it("mostra 'Carregando…' enquanto lista não responde", () => {
    apiMocks.list.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();
  });

  it("renderiza os 5 providers", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    renderPage();
    await waitFor(() => {
      // Cada provider aparece em 2+ lugares (h3 do card + botão "Como obter
      // minha chave do X"); checamos apenas que aparece em pelo menos um.
      expect(screen.getAllByText(/^groq$/i).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/^assemblyai$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/anthropic \(claude\)/i).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText(/openai \(gpt\)/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/google \(gemini\)/i).length).toBeGreaterThan(0);
  });

  it("provider configurado mostra 'Configurada' + última validação", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/^configurada$/i).length).toBe(1);
    });
    expect(screen.getAllByText(/não configurada/i).length).toBe(4);
    // Anthropic tem last_validated_at
    expect(screen.getByText(/última validação/i)).toBeInTheDocument();
    expect(screen.getByText(/✓ válida/i)).toBeInTheDocument();
  });

  it("fluxo 'Salvar e testar' chama test (pre) → save → test (post)", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    apiMocks.test
      .mockResolvedValueOnce({
        provider: "groq",
        status: "valid",
        message: null,
        http_status: 200,
        latency_ms: 50,
      })
      .mockResolvedValueOnce({
        provider: "groq",
        status: "valid",
        message: null,
        http_status: 200,
        latency_ms: 60,
      });
    apiMocks.save.mockResolvedValue({ provider: "groq", is_configured: true });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });

    const groqRow = screen.getByText(/^groq$/i).closest("li")!;
    const input = groqRow.querySelector("input")!;
    await user.type(input, "sk-test-123");
    const saveBtn = Array.from(groqRow.querySelectorAll("button")).find((b) =>
      b.textContent?.toLowerCase().includes("salvar e testar"),
    )!;
    await user.click(saveBtn);

    await waitFor(() => {
      expect(apiMocks.save).toHaveBeenCalledWith("groq", "sk-test-123");
    });
    // Test foi chamado 2x: pré (com key) + pós (sem key)
    expect(apiMocks.test).toHaveBeenCalledWith("groq", "sk-test-123");
    expect(apiMocks.test).toHaveBeenCalledWith("groq");
    // Feedback visual de sucesso aparece
    expect(screen.getByText(/chave validada/i)).toBeInTheDocument();
  });

  it("pré-validação inválida BLOQUEIA o save", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    apiMocks.test.mockResolvedValue({
      provider: "groq",
      status: "invalid",
      message: "Chave rejeitada pelo provider — verifique se digitou correto.",
      http_status: 401,
      latency_ms: 80,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    const groqRow = screen.getByText(/^groq$/i).closest("li")!;
    const input = groqRow.querySelector("input")!;
    await user.type(input, "errada");
    const saveBtn = Array.from(groqRow.querySelectorAll("button")).find((b) =>
      b.textContent?.toLowerCase().includes("salvar e testar"),
    )!;
    await user.click(saveBtn);
    await waitFor(() => {
      // "Chave rejeitada" pode aparecer no banner do test result + texto do guide;
      // basta que apareça pelo menos uma vez
      expect(screen.getAllByText(/chave rejeitada/i).length).toBeGreaterThan(0);
    });
    expect(apiMocks.save).not.toHaveBeenCalled();
  });

  it("botão 'Testar agora' aparece SÓ pra configurados e chama test sem key", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    apiMocks.test.mockResolvedValue({
      provider: "anthropic",
      status: "valid",
      message: null,
      http_status: 200,
      latency_ms: 40,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getAllByText(/anthropic \(claude\)/i).length,
      ).toBeGreaterThan(0);
    });
    const buttons = screen.getAllByRole("button", { name: /testar agora/i });
    expect(buttons.length).toBe(1); // só anthropic está configurada
    await user.click(buttons[0]);
    await waitFor(() => {
      expect(apiMocks.test).toHaveBeenCalledWith("anthropic");
    });
  });

  it("'Como obter minha chave' abre modal com instruções", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    const guideBtn = screen.getAllByRole("button", {
      name: /como obter minha chave do groq/i,
    })[0];
    await user.click(guideBtn);
    // Modal aparece com role dialog
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText(/como obter sua chave do groq/i),
    ).toBeInTheDocument();
  });

  it("erro de top-level quando list falha", async () => {
    apiMocks.list.mockRejectedValue(new Error("network down"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/network down/i)).toBeInTheDocument();
    });
  });

  it("erro de ApiError no save retorna detail", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    apiMocks.test.mockResolvedValue({
      provider: "groq",
      status: "valid",
      message: null,
      http_status: 200,
      latency_ms: 50,
    });
    apiMocks.save.mockRejectedValue(new ApiErrorMock(500, { detail: "boom" }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    const groqRow = screen.getByText(/^groq$/i).closest("li")!;
    const input = groqRow.querySelector("input")!;
    await user.type(input, "x");
    const saveBtn = Array.from(groqRow.querySelectorAll("button")).find((b) =>
      b.textContent?.toLowerCase().includes("salvar e testar"),
    )!;
    await user.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByText(/^boom$/i)).toBeInTheDocument();
    });
  });
});
