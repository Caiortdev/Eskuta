import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    list: vi.fn(),
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: { keys: { list: apiMocks.list } },
  ApiError: apiMocks.ApiError,
}));

import { OnboardingPage } from "./Onboarding";

const NONE_CONFIGURED = {
  providers: ["groq", "assemblyai", "anthropic", "openai", "google"].map(
    (p) => ({
      provider: p,
      is_configured: false,
      last_validated_at: null,
      last_validation_status: null,
      notes: null,
    }),
  ),
};

const ALL_CONFIGURED = {
  providers: ["groq", "assemblyai", "anthropic", "openai", "google"].map(
    (p) => ({
      provider: p,
      is_configured: true,
      last_validated_at: null,
      last_validation_status: null,
      notes: null,
    }),
  ),
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/onboarding"]}>
      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/settings" element={<p>settings landed</p>} />
        <Route path="/" element={<p>home landed</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMocks.list.mockReset();
});

describe("OnboardingPage", () => {
  it("renderiza heading quando nada configurado", async () => {
    apiMocks.list.mockResolvedValue(NONE_CONFIGURED);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        /bem-vindo ao eskuta/i,
      );
    });
  });

  it("explica STT e LLM quando nada configurado", async () => {
    apiMocks.list.mockResolvedValue(NONE_CONFIGURED);
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/STT/).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/LLM/).length).toBeGreaterThan(0);
  });

  it("menciona keyring quando nada configurado", async () => {
    apiMocks.list.mockResolvedValue(NONE_CONFIGURED);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/keyring/i)).toBeInTheDocument();
    });
  });

  it("botão 'Configurar agora' navega pra /settings", async () => {
    apiMocks.list.mockResolvedValue(NONE_CONFIGURED);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /configurar agora/i }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /configurar agora/i }));
    expect(screen.getByText(/settings landed/i)).toBeInTheDocument();
  });

  it("botão 'Pular' navega pra /", async () => {
    apiMocks.list.mockResolvedValue(NONE_CONFIGURED);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /pular/i }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /pular/i }));
    expect(screen.getByText(/home landed/i)).toBeInTheDocument();
  });

  it("pula automaticamente pra Home se já tem STT + LLM configurados", async () => {
    apiMocks.list.mockResolvedValue(ALL_CONFIGURED);
    renderPage();
    // Auto-navegação acontece após list responder
    await waitFor(() => {
      expect(screen.getByText(/home landed/i)).toBeInTheDocument();
    });
  });

  it("mostra 'Verificando configuração' enquanto carrega", () => {
    apiMocks.list.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText(/verificando configura/i)).toBeInTheDocument();
  });

  it("mostra erro quando list falha", async () => {
    apiMocks.list.mockRejectedValue(new Error("network down"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/network down/i)).toBeInTheDocument();
    });
  });
});
