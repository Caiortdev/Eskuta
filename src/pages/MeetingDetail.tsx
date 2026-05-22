/**
 * Tela de detalhes — ata + transcrição + ações em tabs.
 * Botão de evidência por item; sticky header com título / status.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import type {
  ActionItem,
  DecisionItem,
  Evidence,
  MeetingDetail,
} from "@/types/meeting";

type Tab = "ata" | "transcricao" | "acoes";

export function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("ata");

  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    api.meetings
      .get(id)
      .then((res) => {
        if (!abort.signal.aborted) setMeeting(res);
      })
      .catch((err: unknown) => {
        if (abort.signal.aborted) return;
        const msg =
          err instanceof ApiError
            ? (err.detail ?? err.message)
            : err instanceof Error
              ? err.message
              : String(err);
        setError(msg);
      });
    return () => abort.abort();
  }, [id]);

  if (error !== null) {
    return (
      <div className="p-8">
        <h2 className="text-2xl font-semibold tracking-tight">Erro</h2>
        <p className="mt-2 text-sm text-destructive">{error}</p>
        <Link to="/" className="mt-4 inline-block">
          <Button variant="outline">Voltar pra lista</Button>
        </Link>
      </div>
    );
  }

  if (meeting === null) {
    return <div className="p-8 text-sm text-muted-foreground">Carregando…</div>;
  }

  return (
    <div className="p-8 max-w-4xl">
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight truncate">
            {meeting.minutes?.title ??
              meeting.title ??
              meeting.original_filename ??
              "Sem título"}
          </h2>
          <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
            <span>{new Date(meeting.created_at).toLocaleString("pt-BR")}</span>
            <StatusBadge status={meeting.status} />
            {meeting.minutes && (
              <span>
                LLM: {meeting.minutes.llm_provider} · custo $
                {meeting.minutes.cost_usd.toFixed(4)}
              </span>
            )}
          </div>
        </div>
        <Link to="/">
          <Button variant="outline" size="sm">
            Voltar
          </Button>
        </Link>
      </header>

      <div className="mt-6 border-b flex gap-1">
        <TabButton active={tab === "ata"} onClick={() => setTab("ata")}>
          Ata
        </TabButton>
        <TabButton
          active={tab === "transcricao"}
          onClick={() => setTab("transcricao")}
        >
          Transcrição
        </TabButton>
        <TabButton active={tab === "acoes"} onClick={() => setTab("acoes")}>
          Ações ({meeting.minutes?.action_items.length ?? 0})
        </TabButton>
      </div>

      <div className="mt-6">
        {tab === "ata" && <AtaView meeting={meeting} />}
        {tab === "transcricao" && <TranscriptView meeting={meeting} />}
        {tab === "acoes" && <ActionsView meeting={meeting} />}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "-mb-px px-4 py-2 text-sm font-medium border-b-2 transition-colors",
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function AtaView({ meeting }: { meeting: MeetingDetail }) {
  const minutes = meeting.minutes;
  if (!minutes) {
    return (
      <p className="text-sm text-muted-foreground">
        Ata ainda não disponível. Aguarde o processamento ou veja a aba
        Transcrição.
      </p>
    );
  }
  return (
    <div className="space-y-8">
      {!minutes.validation_passed && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700">
          ⚠️ Esta ata tem {minutes.validation_issues?.length ?? 0} item(s) com
          evidência que não pôde ser confirmada na transcrição. Revise antes de
          compartilhar.
        </div>
      )}

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Sumário Executivo
        </h3>
        <p className="mt-2 text-base leading-relaxed">
          {minutes.executive_summary}
        </p>
      </section>

      {minutes.participants.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Participantes
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {minutes.participants.map((name) => (
              <li
                key={name}
                className="rounded-full border bg-muted/30 px-3 py-0.5 text-sm"
              >
                {name}
              </li>
            ))}
          </ul>
        </section>
      )}

      {minutes.topics.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Tópicos
          </h3>
          <ul className="mt-2 space-y-3">
            {minutes.topics.map((topic, i) => (
              <li key={i} className="rounded-md border p-3">
                <h4 className="font-medium">{topic.title}</h4>
                <p className="mt-1 text-sm text-foreground/80">
                  {topic.summary}
                </p>
                {topic.evidence && (
                  <EvidenceQuote
                    evidence={{
                      quote: topic.evidence.quote,
                      speaker: topic.evidence.speaker ?? null,
                      timestamp_sec: topic.evidence.timestamp_sec ?? null,
                    }}
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {minutes.decisions.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Decisões
          </h3>
          <ul className="mt-2 space-y-3">
            {minutes.decisions.map((d) => (
              <li key={d.id} className="rounded-md border p-3">
                <DecisionRow decision={d} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {minutes.open_questions.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Questões em aberto
          </h3>
          <ul className="mt-2 list-disc list-inside space-y-1 text-sm">
            {minutes.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ActionsView({ meeting }: { meeting: MeetingDetail }) {
  const items = meeting.minutes?.action_items ?? [];
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nenhum action item identificado nesta reunião.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.id} className="rounded-md border p-3">
          <ActionRow action={item} />
        </li>
      ))}
    </ul>
  );
}

function TranscriptView({ meeting }: { meeting: MeetingDetail }) {
  const transcript = meeting.transcript;
  if (!transcript) {
    return (
      <p className="text-sm text-muted-foreground">
        Transcrição ainda não disponível.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="text-xs text-muted-foreground">
        {transcript.provider_used} · {transcript.model_used}
        {transcript.word_count !== null && (
          <> · {transcript.word_count} palavras</>
        )}
      </div>
      <ol className="space-y-1">
        {transcript.segments.map((seg, i) => (
          <li key={i} className="text-sm leading-relaxed">
            <span className="mr-2 text-xs text-muted-foreground tabular-nums">
              {formatTimestamp(seg.start_sec)}
              {seg.speaker_id && (
                <>
                  {" "}
                  · {meeting.speaker_map?.[seg.speaker_id] ?? seg.speaker_id}
                </>
              )}
            </span>
            {seg.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

function DecisionRow({ decision }: { decision: DecisionItem }) {
  return (
    <>
      <p className="text-sm">{decision.description}</p>
      {decision.evidence && <EvidenceQuote evidence={decision.evidence} />}
    </>
  );
}

function ActionRow({ action }: { action: ActionItem }) {
  return (
    <>
      <p className="text-sm font-medium">{action.description}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {action.assigned_to ? (
          <>👤 {action.assigned_to}</>
        ) : (
          <span className="italic">Sem responsável atribuído</span>
        )}
        {action.deadline_raw && <> · 📅 {action.deadline_raw}</>}
        {action.status !== "pending" && <> · Status: {action.status}</>}
      </p>
      {action.evidence && <EvidenceQuote evidence={action.evidence} />}
    </>
  );
}

function EvidenceQuote({ evidence }: { evidence: Evidence }) {
  return (
    <blockquote className="mt-2 border-l-2 border-muted-foreground/30 pl-3 text-xs text-muted-foreground italic">
      “{evidence.quote}”{evidence.speaker && <> — {evidence.speaker}</>}
    </blockquote>
  );
}

function formatTimestamp(seconds: number): string {
  const mm = Math.floor(seconds / 60);
  const ss = Math.floor(seconds % 60);
  return `${mm.toString().padStart(2, "0")}:${ss.toString().padStart(2, "0")}`;
}
