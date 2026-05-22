import { render, screen, waitFor } from "@testing-library/react";
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
    ApiError: ApiErrorMock,
  };
});

vi.mock("@/lib/api", () => ({
  api: { meetings: { list: apiMocks.list } },
  ApiError: apiMocks.ApiError,
}));

const ApiErrorMock = apiMocks.ApiError;

import { HomePage } from "./Home";

function renderPage() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMocks.list.mockReset();
});

describe("HomePage", () => {
  it("mostra 'Carregando…' enquanto a request não responde", () => {
    apiMocks.list.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();
  });

  it("mostra empty state quando lista vem vazia", async () => {
    apiMocks.list.mockResolvedValue({
      meetings: [],
      total: 0,
      limit: 100,
      offset: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/nenhuma reunião ainda/i)).toBeInTheDocument();
    });
    expect(
      screen.getByRole("link", { name: /subir arquivo/i }),
    ).toBeInTheDocument();
  });

  it("renderiza card por meeting na lista", async () => {
    apiMocks.list.mockResolvedValue({
      meetings: [
        {
          id: "m1",
          title: "Planning",
          original_filename: "p.mp3",
          duration_sec: 3600,
          file_size_bytes: 1024 * 1024 * 5,
          language: "pt",
          source: "upload",
          status: "completed",
          created_at: "2026-05-22T12:00:00Z",
        },
        {
          id: "m2",
          title: null,
          original_filename: "outra.mp3",
          duration_sec: null,
          file_size_bytes: null,
          language: "pt",
          source: "upload",
          status: "transcribing",
          created_at: "2026-05-22T13:00:00Z",
        },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/planning/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/outra\.mp3/)).toBeInTheDocument();
  });

  it("mostra erro quando a request falha", async () => {
    apiMocks.list.mockRejectedValue(new Error("connection refused"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/erro ao carregar/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/connection refused/i)).toBeInTheDocument();
  });

  it("mostra detail do ApiError quando rejeitado com ApiError", async () => {
    apiMocks.list.mockRejectedValue(
      new ApiErrorMock(500, { detail: "boom interno" }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/boom interno/i)).toBeInTheDocument();
    });
  });

  it("link 'Nova reunião' aparece no header", async () => {
    apiMocks.list.mockResolvedValue({
      meetings: [],
      total: 0,
      limit: 100,
      offset: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /nova reunião/i }),
      ).toBeInTheDocument();
    });
  });
});
