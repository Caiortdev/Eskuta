import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

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

vi.mock("@/lib/api", () => ({
  api: { meetings: { get: apiMocks.get } },
  ApiError: ApiErrorMock,
}));

import { MeetingDetailPage } from "./MeetingDetail";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/meetings/m1"]}>
      <Routes>
        <Route path="/meetings/:id" element={<MeetingDetailPage />} />
        <Route path="/" element={<p>home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const FULL_MEETING = {
  id: "m1",
  title: null,
  original_filename: "audio.mp3",
  audio_path: "/x/audio.mp3",
  audio_hash: "abc",
  duration_sec: 600,
  file_size_bytes: 1000,
  language: "pt",
  source: "upload",
  status: "completed" as const,
  speaker_map: null,
  extra_metadata: null,
  started_at: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T11:00:00Z",
  transcript: {
    id: "t1",
    full_text: "olá mundo",
    language_detected: "pt",
    provider_used: "groq",
    model_used: "whisper-large-v3-turbo",
    word_count: 2,
    segments: [
      {
        start_sec: 0,
        end_sec: 2,
        text: "olá",
        speaker_id: "SPEAKER_00",
        confidence: 0.95,
      },
      {
        start_sec: 2,
        end_sec: 5,
        text: "mundo",
        speaker_id: null,
        confidence: null,
      },
    ],
  },
  minutes: {
    id: "min1",
    title: "Ata teste",
    date_extracted: null,
    executive_summary: "Resumo da reunião",
    participants: ["João", "Maria"],
    topics: [
      {
        title: "T1",
        summary: "Discutido T1",
        evidence: { quote: "trecho T1", speaker: "João", timestamp_sec: 1 },
      },
    ],
    open_questions: ["Pergunta?"],
    decisions: [
      {
        id: "d1",
        description: "Decisão 1",
        evidence: { quote: "trecho dec", speaker: null, timestamp_sec: null },
      },
    ],
    action_items: [
      {
        id: "a1",
        description: "Ação 1",
        assigned_to: "João",
        deadline_raw: "sexta",
        deadline_parsed: null,
        priority: "normal" as const,
        status: "pending" as const,
        evidence: { quote: "trecho ação", speaker: null, timestamp_sec: null },
      },
    ],
    llm_provider: "claude",
    llm_model: "claude-sonnet-4-5",
    tokens_input: 100,
    tokens_output: 50,
    cost_usd: 0.0165,
    validation_passed: true,
    validation_issues: null,
  },
};

beforeEach(() => {
  apiMocks.get.mockReset();
});

describe("MeetingDetailPage", () => {
  it("mostra 'Carregando…' enquanto request não responde", () => {
    apiMocks.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();
  });

  it("renderiza heading + tabs após carregar", async () => {
    apiMocks.get.mockResolvedValue(FULL_MEETING);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ata teste/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^ata$/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /transcrição/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ações \(1\)/i }),
    ).toBeInTheDocument();
  });

  it("aba Ata renderiza sumário + decisões + tópicos por default", async () => {
    apiMocks.get.mockResolvedValue(FULL_MEETING);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/resumo da reunião/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/decisão 1/i)).toBeInTheDocument();
    expect(screen.getByText(/discutido t1/i)).toBeInTheDocument();
    expect(screen.getByText(/pergunta\?/i)).toBeInTheDocument();
  });

  it("aba Transcrição mostra segments", async () => {
    apiMocks.get.mockResolvedValue(FULL_MEETING);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ata teste/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /transcrição/i }));
    expect(screen.getByText(/^olá$/i)).toBeInTheDocument();
    expect(screen.getByText(/^mundo$/i)).toBeInTheDocument();
  });

  it("aba Ações mostra action_items", async () => {
    apiMocks.get.mockResolvedValue(FULL_MEETING);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ata teste/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /ações \(1\)/i }));
    expect(screen.getByText(/ação 1/i)).toBeInTheDocument();
  });

  it("warning aparece quando validation_passed=false", async () => {
    apiMocks.get.mockResolvedValue({
      ...FULL_MEETING,
      minutes: {
        ...FULL_MEETING.minutes,
        validation_passed: false,
        validation_issues: [{ x: 1 }, { x: 2 }],
      },
    });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/2 item\(s\) com evidência/i),
      ).toBeInTheDocument();
    });
  });

  it("mostra erro quando request falha", async () => {
    apiMocks.get.mockRejectedValue(new Error("not found"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/^erro$/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });

  it("meeting sem transcript+minutes mostra mensagens apropriadas", async () => {
    apiMocks.get.mockResolvedValue({
      ...FULL_MEETING,
      transcript: null,
      minutes: null,
      status: "pending" as const,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/ata ainda não disponível/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /transcrição/i }));
    expect(
      screen.getByText(/transcrição ainda não disponível/i),
    ).toBeInTheDocument();
  });
});
