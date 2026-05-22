import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, waitForSidecar } from "./api";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

// ============================================================
// ApiError
// ============================================================

describe("ApiError", () => {
  it("é instância de Error", () => {
    const err = new ApiError(404, { msg: "not found" });
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
  });

  it("detail extrai 'detail' do body no formato FastAPI", () => {
    const err = new ApiError(422, { detail: "validation failed" });
    expect(err.detail).toBe("validation failed");
  });

  it("detail retorna null quando body não tem detail", () => {
    expect(new ApiError(500, "raw text").detail).toBeNull();
    expect(new ApiError(500, null).detail).toBeNull();
    expect(new ApiError(500, { detail: 42 }).detail).toBeNull();
  });
});

// ============================================================
// api.health
// ============================================================

describe("api.health", () => {
  it("retorna payload em sucesso", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ status: "ok", version: "0.1.0" }),
    );

    const result = await api.health();
    expect(result).toEqual({ status: "ok", version: "0.1.0" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("chama localhost:8765 (nunca origem externa)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ status: "ok", version: "0.1.0" }),
    );
    await api.health();
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toMatch(/^http:\/\/127\.0\.0\.1:8765/);
  });

  it("lança ApiError com status e body em erro HTTP", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    );

    await expect(api.health()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      body: { detail: "boom" },
    });
  });
});

// ============================================================
// api.meetings
// ============================================================

describe("api.meetings.list", () => {
  it("aceita query params opcionais", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ meetings: [], total: 0, limit: 10, offset: 5 }),
    );
    await api.meetings.list({ limit: 10, offset: 5 });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=5");
  });

  it("omite query string quando sem params", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ meetings: [], total: 0, limit: 50, offset: 0 }),
    );
    await api.meetings.list();
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toMatch(/\/meetings$/);
  });
});

describe("api.meetings.upload", () => {
  it("envia FormData via POST sem Content-Type explícito", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "abc",
          status: "pending",
          title: null,
          original_filename: "x.mp3",
          file_size_bytes: 100,
        },
        { status: 201 },
      ),
    );
    const file = new File([new Uint8Array(100)], "x.mp3", {
      type: "audio/mpeg",
    });
    const result = await api.meetings.upload(file);
    expect(result.id).toBe("abc");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    // O browser injeta o Content-Type multipart/form-data com boundary
    // automaticamente — NÃO devemos setar manualmente
    expect(init.headers).toBeUndefined();
  });

  it("anexa title e language como query params", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: "x",
          status: "pending",
          title: "Planning",
          original_filename: "x.mp3",
          file_size_bytes: 1,
        },
        { status: 201 },
      ),
    );
    const file = new File([""], "x.mp3");
    await api.meetings.upload(file, { title: "Planning", language: "pt" });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("title=Planning");
    expect(url).toContain("language=pt");
  });
});

describe("api.meetings.status / updateSpeakerMap / delete", () => {
  it("status chama GET /meetings/:id/status", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: "abc", status: "transcribing", error: null }),
    );
    await api.meetings.status("abc");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(
      /\/meetings\/abc\/status$/,
    );
  });

  it("updateSpeakerMap manda PUT com body JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ id: "abc", speaker_map: { SPEAKER_00: "João" } }),
    );
    await api.meetings.updateSpeakerMap("abc", { SPEAKER_00: "João" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      speaker_map: { SPEAKER_00: "João" },
    });
  });

  it("delete manda DELETE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "abc", deleted: true }));
    await api.meetings.delete("abc");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("DELETE");
  });
});

// ============================================================
// api.keys
// ============================================================

describe("api.keys", () => {
  it("save manda PUT /api/keys/:provider com body { key }", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ provider: "groq", is_configured: true }),
    );
    await api.keys.save("groq", "sk-test");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ key: "sk-test" });
  });

  it("delete manda DELETE /api/keys/:provider", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ provider: "groq", is_configured: false }),
    );
    await api.keys.delete("groq");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("DELETE");
  });
});

// ============================================================
// waitForSidecar
// ============================================================

describe("waitForSidecar", () => {
  it("retorna na primeira tentativa quando sidecar já está pronto", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ status: "ok", version: "0.1.0" }),
    );

    const result = await waitForSidecar({ intervalMs: 10, timeoutMs: 1000 });
    expect(result.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("faz retry até o sidecar responder ok", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockResolvedValueOnce(jsonResponse({ status: "ok", version: "0.1.0" }));

    const result = await waitForSidecar({ intervalMs: 5, timeoutMs: 1000 });
    expect(result.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("lança erro quando estoura o timeout", async () => {
    fetchMock.mockRejectedValue(new Error("connection refused"));

    await expect(
      waitForSidecar({ intervalMs: 5, timeoutMs: 30 }),
    ).rejects.toThrow(/Sidecar não respondeu/);
  });

  it("aborta quando recebe sinal de cancelamento", async () => {
    fetchMock.mockRejectedValue(new Error("connection refused"));
    const abort = new AbortController();
    setTimeout(() => abort.abort(), 10);

    await expect(
      waitForSidecar({
        intervalMs: 5,
        timeoutMs: 5000,
        signal: abort.signal,
      }),
    ).rejects.toBeDefined();
  });
});
