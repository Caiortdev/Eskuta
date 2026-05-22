import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock é hoisted — então a captura do onDrop e mocks da api ficam dentro
// do factory vi.hoisted() (mesmo padrão de Settings/Home/MeetingDetail).
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
  // Holder pro callback onDrop do dropzone — preenchido a cada render.
  const dropzone: {
    lastOnDrop: ((files: File[]) => void | Promise<void>) | null;
  } = { lastOnDrop: null };
  return {
    upload: vi.fn(),
    ApiError: ApiErrorMock,
    dropzone,
  };
});

vi.mock("@/lib/api", () => ({
  api: { meetings: { upload: apiMocks.upload } },
  ApiError: apiMocks.ApiError,
}));

vi.mock("react-dropzone", () => ({
  useDropzone: (opts: { onDrop: (files: File[]) => void | Promise<void> }) => {
    apiMocks.dropzone.lastOnDrop = opts.onDrop;
    return {
      getRootProps: () => ({ "data-testid": "dz-root" }),
      getInputProps: () => ({ "data-testid": "dz-input" }),
      isDragActive: false,
    };
  },
}));

const ApiErrorMock = apiMocks.ApiError;

import { UploadPage } from "./Upload";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/processing/:id" element={<p>processing landed</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function makeFile(name = "x.mp3", size = 1024, type = "audio/mpeg"): File {
  const blob = new Blob([new Uint8Array(size)], { type });
  return new File([blob], name, { type });
}

beforeEach(() => {
  apiMocks.upload.mockReset();
  apiMocks.dropzone.lastOnDrop = null;
});

describe("UploadPage", () => {
  it("renderiza heading e instrução do dropzone", () => {
    renderPage();
    expect(screen.getByText(/nova reunião/i)).toBeInTheDocument();
    expect(screen.getByText(/arraste o áudio/i)).toBeInTheDocument();
  });

  it("aceita digitação no input de título (controlled)", async () => {
    const user = userEvent.setup();
    renderPage();
    const input = screen.getByLabelText(/título/i);
    await user.type(input, "Planning");
    expect((input as HTMLInputElement).value).toBe("Planning");
  });

  it("onDrop vazio é no-op (não chama api)", async () => {
    renderPage();
    expect(apiMocks.dropzone.lastOnDrop).not.toBeNull();
    await apiMocks.dropzone.lastOnDrop!([]);
    expect(apiMocks.upload).not.toHaveBeenCalled();
  });

  it("upload bem-sucedido chama api.meetings.upload e navega pra /processing/:id", async () => {
    apiMocks.upload.mockResolvedValue({ id: "m42" });
    renderPage();
    const file = makeFile();
    await apiMocks.dropzone.lastOnDrop!([file]);
    expect(apiMocks.upload).toHaveBeenCalledWith(file, { title: undefined });
    await waitFor(() => {
      expect(screen.getByText(/processing landed/i)).toBeInTheDocument();
    });
  });

  it("upload envia title quando preenchido", async () => {
    apiMocks.upload.mockResolvedValue({ id: "m1" });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/título/i), "Sprint Review");
    const file = makeFile();
    await apiMocks.dropzone.lastOnDrop!([file]);
    expect(apiMocks.upload).toHaveBeenCalledWith(file, {
      title: "Sprint Review",
    });
  });

  it("ApiError mostra detail no banner de erro", async () => {
    apiMocks.upload.mockRejectedValue(
      new ApiErrorMock(413, { detail: "arquivo grande demais" }),
    );
    renderPage();
    await apiMocks.dropzone.lastOnDrop!([makeFile()]);
    await waitFor(() => {
      expect(screen.getByText(/falha no upload/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/arquivo grande demais/i)).toBeInTheDocument();
  });

  it("Error genérico mostra .message", async () => {
    apiMocks.upload.mockRejectedValue(new Error("network down"));
    renderPage();
    await apiMocks.dropzone.lastOnDrop!([makeFile()]);
    await waitFor(() => {
      expect(screen.getByText(/network down/i)).toBeInTheDocument();
    });
  });

  it("rejeição com não-Error usa String(err)", async () => {
    apiMocks.upload.mockRejectedValue("boom string");
    renderPage();
    await apiMocks.dropzone.lastOnDrop!([makeFile()]);
    await waitFor(() => {
      expect(screen.getByText(/boom string/i)).toBeInTheDocument();
    });
  });

  it("botão 'Tentar de novo' reseta pra idle (some o banner)", async () => {
    apiMocks.upload.mockRejectedValue(new Error("falha"));
    const user = userEvent.setup();
    renderPage();
    await apiMocks.dropzone.lastOnDrop!([makeFile()]);
    await waitFor(() => {
      expect(screen.getByText(/falha no upload/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /tentar de novo/i }));
    expect(screen.queryByText(/falha no upload/i)).not.toBeInTheDocument();
  });
});
