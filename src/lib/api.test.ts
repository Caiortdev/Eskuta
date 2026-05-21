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

describe("api.health", () => {
  it("retorna payload em sucesso", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await api.health();
    expect(result).toEqual({ status: "ok", version: "0.1.0" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("chama localhost:8765 (nunca origem externa)", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
      }),
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

  it("ApiError é instância de Error", () => {
    const err = new ApiError(404, { msg: "not found" });
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
  });
});

describe("waitForSidecar", () => {
  it("retorna na primeira tentativa quando sidecar já está pronto", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
      }),
    );

    const result = await waitForSidecar({ intervalMs: 10, timeoutMs: 1000 });
    expect(result.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("faz retry até o sidecar responder ok", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
          status: 200,
        }),
      );

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
