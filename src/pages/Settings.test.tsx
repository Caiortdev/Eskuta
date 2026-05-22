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
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: {
    keys: { list: apiMocks.list, save: apiMocks.save, delete: apiMocks.delete },
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
    last_validated_at: null,
    last_validation_status: null,
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
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/^assemblyai$/i)).toBeInTheDocument();
    expect(screen.getByText(/anthropic \(claude\)/i)).toBeInTheDocument();
    expect(screen.getByText(/openai \(gpt\)/i)).toBeInTheDocument();
    expect(screen.getByText(/google \(gemini\)/i)).toBeInTheDocument();
  });

  it("provider configurado mostra 'Configurada'", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/^configurada$/i).length).toBe(1);
    });
    expect(screen.getAllByText(/não configurada/i).length).toBe(4);
  });

  it("salvar uma key chama api.keys.save com provider correto", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
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
      b.textContent?.toLowerCase().includes("salvar"),
    )!;
    await user.click(saveBtn);

    expect(apiMocks.save).toHaveBeenCalledWith("groq", "sk-test-123");
  });

  it("error message aparece quando save falha", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    apiMocks.save.mockRejectedValue(
      new ApiErrorMock(401, { detail: "key inválida" }),
    );
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    const groqRow = screen.getByText(/^groq$/i).closest("li")!;
    const input = groqRow.querySelector("input")!;
    await user.type(input, "x");
    const saveBtn = Array.from(groqRow.querySelectorAll("button")).find((b) =>
      b.textContent?.toLowerCase().includes("salvar"),
    )!;
    await user.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByText(/key inválida/i)).toBeInTheDocument();
    });
  });

  it("botão 'Remover' aparece SÓ pra providers configurados", async () => {
    apiMocks.list.mockResolvedValue({ providers: ALL_PROVIDERS });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^groq$/i)).toBeInTheDocument();
    });
    // Apenas 1 botão remover (anthropic está configured)
    expect(screen.getAllByRole("button", { name: /remover/i }).length).toBe(1);
  });

  it("mostra erro de top-level quando list falha", async () => {
    apiMocks.list.mockRejectedValue(new Error("network down"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/network down/i)).toBeInTheDocument();
    });
  });
});
