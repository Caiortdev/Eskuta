/**
 * Configurações — gerenciamento de API keys (STT + LLM).
 * Form simples: input + salvar/remover por provider.
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ApiKeyProvider, ProviderStatus } from "@/types/meeting";

const PROVIDER_LABELS: Record<ApiKeyProvider, { name: string; hint: string }> =
  {
    groq: {
      name: "Groq",
      hint: "STT primário · Whisper Large v3 Turbo · console.groq.com/keys",
    },
    assemblyai: {
      name: "AssemblyAI",
      hint: "STT fallback · 100h/mês grátis · assemblyai.com",
    },
    anthropic: {
      name: "Anthropic (Claude)",
      hint: "LLM recomendado pra ata · console.anthropic.com",
    },
    openai: {
      name: "OpenAI (GPT)",
      hint: "LLM alternativo · platform.openai.com",
    },
    google: {
      name: "Google (Gemini)",
      hint: "LLM mais barato · ai.google.dev",
    },
  };

export function SettingsPage() {
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const res = await api.keys.list();
      setProviders(res.providers);
    } catch (err) {
      setError(formatError(err));
    }
  };

  useEffect(() => {
    let cancelled = false;
    api.keys
      .list()
      .then((res) => {
        if (!cancelled) setProviders(res.providers);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(formatError(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="p-8 max-w-2xl">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Configurações</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          API keys são guardadas no keyring do seu sistema (Credential Manager
          no Windows, Keychain no macOS). Nunca em arquivo local.
        </p>
      </header>

      {error && (
        <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {providers === null ? (
        <p className="mt-6 text-sm text-muted-foreground">Carregando…</p>
      ) : (
        <ul className="mt-6 space-y-4">
          {providers.map((p) => (
            <li key={p.provider} className="rounded-md border p-4">
              <ProviderRow
                status={p}
                onSaved={() => void refresh()}
                onDeleted={() => void refresh()}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProviderRow({
  status,
  onSaved,
  onDeleted,
}: {
  status: ProviderStatus;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const meta = PROVIDER_LABELS[status.provider];
  const [keyInput, setKeyInput] = useState("");
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const save = async () => {
    setPending(true);
    setActionError(null);
    try {
      await api.keys.save(status.provider, keyInput.trim());
      setKeyInput("");
      onSaved();
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setPending(false);
    }
  };

  const remove = async () => {
    if (!confirm(`Remover a API key do ${meta.name}?`)) return;
    setPending(true);
    setActionError(null);
    try {
      await api.keys.delete(status.provider);
      onDeleted();
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium">{meta.name}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{meta.hint}</p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
            status.is_configured
              ? "bg-emerald-500/10 text-emerald-700"
              : "bg-muted text-muted-foreground",
          )}
        >
          <span
            className={cn(
              "size-1.5 rounded-full",
              status.is_configured
                ? "bg-emerald-500"
                : "bg-muted-foreground/50",
            )}
          />
          {status.is_configured ? "Configurada" : "Não configurada"}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          type="password"
          autoComplete="off"
          value={keyInput}
          onChange={(e) => setKeyInput(e.currentTarget.value)}
          placeholder={status.is_configured ? "Substituir key…" : "Nova key…"}
          className={cn(
            "flex-1 rounded-md border bg-transparent px-3 py-1.5 text-sm font-mono",
            "placeholder:text-muted-foreground",
            "focus:outline-none focus:ring-2 focus:ring-ring",
          )}
          disabled={pending}
        />
        <Button
          type="button"
          size="sm"
          onClick={save}
          disabled={pending || keyInput.trim().length === 0}
        >
          Salvar
        </Button>
        {status.is_configured && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={remove}
            disabled={pending}
          >
            Remover
          </Button>
        )}
      </div>
      {actionError && (
        <p className="mt-2 text-xs text-destructive">{actionError}</p>
      )}
    </>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}
