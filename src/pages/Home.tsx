/**
 * Home / Dashboard — lista de reuniões processadas.
 * Card por reunião + link pra detail. Botão "Nova reunião" leva pra /upload.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import type { MeetingListItem } from "@/types/meeting";

export function HomePage() {
  const [meetings, setMeetings] = useState<MeetingListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    api.meetings
      .list({ limit: 100 })
      .then((response) => {
        if (!abort.signal.aborted) {
          setMeetings(response.meetings);
        }
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
  }, []);

  if (error !== null) {
    return (
      <div className="p-8">
        <PageHeader />
        <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Erro ao carregar reuniões: {error}
        </div>
      </div>
    );
  }

  if (meetings === null) {
    return (
      <div className="p-8">
        <PageHeader />
        <p className="mt-8 text-sm text-muted-foreground">Carregando…</p>
      </div>
    );
  }

  if (meetings.length === 0) {
    return (
      <div className="p-8">
        <PageHeader />
        <EmptyState
          title="Nenhuma reunião ainda"
          description="Faça upload do seu primeiro arquivo de áudio pra gerar a primeira ata."
          action={
            <Link to="/upload">
              <Button>Subir arquivo</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <PageHeader />
      <ul className="mt-6 space-y-3">
        {meetings.map((m) => (
          <li key={m.id}>
            <MeetingCard meeting={m} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function PageHeader() {
  return (
    <header className="flex items-center justify-between">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Reuniões</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Histórico de áudios processados.
        </p>
      </div>
      <Link to="/upload">
        <Button>Nova reunião</Button>
      </Link>
    </header>
  );
}

function MeetingCard({ meeting }: { meeting: MeetingListItem }) {
  const target =
    meeting.status === "completed"
      ? `/meetings/${meeting.id}`
      : `/processing/${meeting.id}`;
  const created = new Date(meeting.created_at);
  return (
    <Link
      to={target}
      className="block rounded-lg border bg-card p-4 hover:bg-muted/40 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-medium truncate">
            {meeting.title ?? meeting.original_filename ?? "Sem título"}
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {created.toLocaleString("pt-BR")}
            {meeting.duration_sec !== null && (
              <> · {formatDuration(meeting.duration_sec)}</>
            )}
            {meeting.file_size_bytes !== null && (
              <> · {formatSize(meeting.file_size_bytes)}</>
            )}
          </p>
        </div>
        <StatusBadge status={meeting.status} />
      </div>
    </Link>
  );
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins ? `${hours}h ${mins}min` : `${hours}h`;
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${mb.toFixed(1)}MB`;
}
