/**
 * Cliente HTTP do app Eskuta para o sidecar local (FastAPI na porta 8765).
 *
 * Toda comunicação fica em localhost — o sidecar nunca aceita conexão
 * externa. Erros são tipados via `ApiError` pra a UI tratar consistente.
 *
 * Endpoints organizados por recurso (api.meetings, api.keys, etc).
 */

import type {
  ApiKeyProvider,
  DeleteResponse,
  MeetingCreated,
  MeetingDetail,
  MeetingListResponse,
  MeetingStatusResponse,
  ProvidersListResponse,
  SimpleStatusResponse,
  SpeakerMap,
} from "@/types/meeting";

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

  /** Tenta extrair `detail` (formato FastAPI) — útil pra UI exibir. */
  get detail(): string | null {
    if (this.body && typeof this.body === "object" && "detail" in this.body) {
      const detail = (this.body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
    return null;
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

/** Upload usa multipart — não setar Content-Type (browser fornece boundary). */
async function requestForm<T>(
  path: string,
  formData: FormData,
  init?: Omit<RequestInit, "body" | "headers">,
): Promise<T> {
  const res = await fetch(`${SIDECAR_BASE_URL}${path}`, {
    ...init,
    method: init?.method ?? "POST",
    body: formData,
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

// =============================================================
// Endpoints organizados por recurso
// =============================================================

export const api = {
  health: () => request<HealthResponse>("/health"),

  meetings: {
    list: (params: { limit?: number; offset?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.limit !== undefined) qs.set("limit", String(params.limit));
      if (params.offset !== undefined) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request<MeetingListResponse>(`/meetings${suffix}`);
    },

    get: (id: string) => request<MeetingDetail>(`/meetings/${id}`),

    status: (id: string) =>
      request<MeetingStatusResponse>(`/meetings/${id}/status`),

    upload: (file: File, options?: { title?: string; language?: string }) => {
      const formData = new FormData();
      formData.append("file", file);
      const qs = new URLSearchParams();
      if (options?.title) qs.set("title", options.title);
      if (options?.language) qs.set("language", options.language);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return requestForm<MeetingCreated>(`/meetings/upload${suffix}`, formData);
    },

    updateSpeakerMap: (id: string, speakerMap: Record<string, string>) =>
      request<SpeakerMap>(`/meetings/${id}/speaker-map`, {
        method: "PUT",
        body: JSON.stringify({ speaker_map: speakerMap }),
      }),

    delete: (id: string) =>
      request<DeleteResponse>(`/meetings/${id}`, { method: "DELETE" }),
  },

  keys: {
    list: () => request<ProvidersListResponse>("/api/keys"),

    save: (provider: ApiKeyProvider, key: string) =>
      request<SimpleStatusResponse>(`/api/keys/${provider}`, {
        method: "PUT",
        body: JSON.stringify({ key }),
      }),

    delete: (provider: ApiKeyProvider) =>
      request<SimpleStatusResponse>(`/api/keys/${provider}`, {
        method: "DELETE",
      }),
  },

  transcribe: {
    start: (meetingId: string) =>
      request<{ status: string; meeting_id: string }>("/transcribe/start", {
        method: "POST",
        body: JSON.stringify({ meeting_id: meetingId }),
      }),
  },
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
