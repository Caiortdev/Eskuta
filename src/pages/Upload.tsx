/**
 * Tela de upload — drag-drop via react-dropzone + validação de tamanho/formato
 * + redireciona pra /processing/:id após sucesso.
 */

import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAX_BYTES = 500 * 1024 * 1024; // 500MB
const ACCEPT = {
  "audio/mpeg": [".mp3"],
  "audio/mp4": [".mp4", ".m4a"],
  "audio/wav": [".wav"],
  "audio/x-wav": [".wav"],
  "video/mp4": [".mp4"],
};

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; file: File }
  | { kind: "error"; message: string };

export function UploadPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<UploadState>({ kind: "idle" });
  const [title, setTitle] = useState("");

  const onDrop = async (accepted: File[]) => {
    if (accepted.length === 0) return;
    const file = accepted[0];
    setState({ kind: "uploading", file });
    try {
      const result = await api.meetings.upload(file, {
        title: title.trim() || undefined,
      });
      navigate(`/processing/${result.id}`);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? (err.detail ?? err.message)
          : err instanceof Error
            ? err.message
            : String(err);
      setState({ kind: "error", message });
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    multiple: false,
    maxSize: MAX_BYTES,
    disabled: state.kind === "uploading",
  });

  return (
    <div className="p-8 max-w-2xl">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Nova reunião</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          MP3, MP4, M4A ou WAV. Limite de 500MB.
        </p>
      </header>

      <div className="mt-6 space-y-4">
        <div>
          <label
            htmlFor="meeting-title"
            className="block text-sm font-medium mb-1.5"
          >
            Título (opcional)
          </label>
          <input
            id="meeting-title"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            placeholder="Ex: Planning Sprint 12"
            className={cn(
              "w-full rounded-md border bg-transparent px-3 py-2 text-sm",
              "placeholder:text-muted-foreground",
              "focus:outline-none focus:ring-2 focus:ring-ring",
            )}
            disabled={state.kind === "uploading"}
          />
        </div>

        <div
          {...getRootProps()}
          className={cn(
            "rounded-lg border-2 border-dashed p-10 text-center cursor-pointer transition-colors",
            isDragActive
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50",
            state.kind === "uploading" && "opacity-60 cursor-progress",
          )}
        >
          <input {...getInputProps()} />
          {state.kind === "uploading" ? (
            <p className="text-sm">
              Enviando <strong>{state.file.name}</strong>…
            </p>
          ) : (
            <>
              <p className="text-base font-medium">
                {isDragActive
                  ? "Solte o arquivo aqui…"
                  : "Arraste o áudio ou clique pra escolher"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                MP3, MP4, M4A, WAV · máximo 500MB
              </p>
            </>
          )}
        </div>

        {state.kind === "error" && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <strong>Falha no upload:</strong> {state.message}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="ml-3"
              onClick={() => setState({ kind: "idle" })}
            >
              Tentar de novo
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
