/**
 * Cliente HTTP do app Eskuta para o sidecar local (FastAPI na porta 8765).
 *
 * Toda comunicação fica em localhost — o sidecar nunca aceita conexão
 * externa. Erros são tipados via `ApiError` pra a UI tratar consistente.
 */

const SIDECAR_BASE_URL = "http://127.0.0.1:8765";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `Sidecar respondeu ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface HealthResponse {
  status: "ok";
  version: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${SIDECAR_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  const text = await res.text();
  const body: unknown = text ? safeJsonParse(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, body);
  }

  return body as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  health: () => request<HealthResponse>("/health"),
};

/**
 * Faz polling do endpoint /health do sidecar até obter resposta ok ou
 * estourar o número máximo de tentativas. Usado no boot do app, enquanto
 * o sidecar (Python via PyInstaller) sobe.
 */
export async function waitForSidecar(options?: {
  intervalMs?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
}): Promise<HealthResponse> {
  const intervalMs = options?.intervalMs ?? 500;
  const timeoutMs = options?.timeoutMs ?? 30_000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    options?.signal?.throwIfAborted?.();
    try {
      return await api.health();
    } catch {
      // sidecar ainda subindo — segue tentando
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(
    `Sidecar não respondeu em ${timeoutMs}ms. Veja os logs em ~/.eskuta/logs/.`,
  );
}
