/**
 * Configurações — gerenciamento de API keys (STT + LLM).
 *
 * Cada provider tem:
 * - Status atual (configurado/não, última validação)
 * - Botão "Como obter minha chave" (abre ApiKeyGuideModal com passo a passo)
 * - Input + botão "Salvar e testar" (salva no keyring e testa contra o provider)
 * - Botão "Testar agora" (revalida key já salva)
 * - Botão "Remover" (idempotente, pede confirmação)
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { ApiKeyGuideModal } from "@/components/ApiKeyGuideModal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ApiKeyProvider,
  ProviderStatus,
  TestKeyResponse,
} from "@/types/meeting";

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
  const [guideFor, setGuideFor] = useState<ApiKeyProvider | null>(null);

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
                onShowGuide={() => setGuideFor(p.provider)}
              />
            </li>
          ))}
        </ul>
      )}

      <DiagnosticsSection />

      {guideFor && (
        <ApiKeyGuideModal
          provider={guideFor}
          onClose={() => setGuideFor(null)}
        />
      )}
    </div>
  );
}

function DiagnosticsSection() {
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const exportLogs = async () => {
    setPending(true);
    setActionError(null);
    try {
      const blob = await api.diagnostics.exportLogs();
      const url = URL.createObjectURL(blob);
      // Cria um <a> efêmero e dispara o download
      const a = document.createElement("a");
      a.href = url;
      a.download = "eskuta-diagnostics.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="mt-10 rounded-md border p-4">
      <h3 className="font-medium">Diagnóstico</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Exporte um ZIP com os logs do app (com API keys mascaradas) pra anexar
        em report de bug.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={exportLogs}
          disabled={pending}
        >
          {pending ? "Gerando…" : "Exportar logs"}
        </Button>
      </div>
      {actionError && (
        <p className="mt-2 text-xs text-destructive">{actionError}</p>
      )}
    </section>
  );
}

function ProviderRow({
  status,
  onSaved,
  onDeleted,
  onShowGuide,
}: {
  status: ProviderStatus;
  onSaved: () => void;
  onDeleted: () => void;
  onShowGuide: () => void;
}) {
  const meta = PROVIDER_LABELS[status.provider];
  const [keyInput, setKeyInput] = useState("");
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestKeyResponse | null>(null);

  const saveAndTest = async () => {
    setPending(true);
    setActionError(null);
    setTestResult(null);
    try {
      // 1) Pré-valida o valor novo SEM persistir (evita salvar lixo no keyring)
      const pre = await api.keys.test(status.provider, keyInput.trim());
      if (pre.status === "invalid") {
        setTestResult(pre);
        // Não salva
        return;
      }
      // 2) Salva no keyring
      await api.keys.save(status.provider, keyInput.trim());
      // 3) Re-testa a chave salva (pra registrar last_validated_at no DB)
      const post = await api.keys.test(status.provider);
      setTestResult(post);
      setKeyInput("");
      onSaved();
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setPending(false);
    }
  };

  const testStored = async () => {
    setPending(true);
    setActionError(null);
    setTestResult(null);
    try {
      const res = await api.keys.test(status.provider);
      setTestResult(res);
      onSaved(); // refresh pra puxar last_validated_at atualizado
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
    setTestResult(null);
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
          {status.last_validated_at && (
            <p className="mt-1 text-xs text-muted-foreground">
              Última validação: {formatValidationTime(status.last_validated_at)}{" "}
              · status: {formatValidationStatus(status.last_validation_status)}
            </p>
          )}
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

      <div className="mt-3">
        <button
          type="button"
          onClick={onShowGuide}
          className="text-xs text-primary underline-offset-2 hover:underline focus:outline-none focus:ring-2 focus:ring-ring rounded"
        >
          Como obter minha chave do {meta.name} →
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          type="password"
          autoComplete="off"
          value={keyInput}
          onChange={(e) => setKeyInput(e.currentTarget.value)}
          placeholder={status.is_configured ? "Substituir key…" : "Nova key…"}
          className={cn(
            "flex-1 min-w-[200px] rounded-md border bg-transparent px-3 py-1.5 text-sm font-mono",
            "placeholder:text-muted-foreground",
            "focus:outline-none focus:ring-2 focus:ring-ring",
          )}
          disabled={pending}
        />
        <Button
          type="button"
          size="sm"
          onClick={saveAndTest}
          disabled={pending || keyInput.trim().length === 0}
        >
          {pending ? "…" : "Salvar e testar"}
        </Button>
        {status.is_configured && (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={testStored}
              disabled={pending}
            >
              Testar agora
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={remove}
              disabled={pending}
            >
              Remover
            </Button>
          </>
        )}
      </div>

      {testResult && (
        <div
          className={cn(
            "mt-3 rounded-md border p-3 text-xs",
            testResult.status === "valid"
              ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-900 dark:text-emerald-200"
              : testResult.status === "invalid"
                ? "border-destructive/30 bg-destructive/5 text-destructive"
                : "border-amber-500/30 bg-amber-500/5 text-amber-900 dark:text-amber-200",
          )}
        >
          <strong>
            {testResult.status === "valid"
              ? "✓ Chave validada"
              : testResult.status === "invalid"
                ? "✗ Chave rejeitada"
                : "⚠ Erro temporário"}
          </strong>
          {testResult.message && <> — {testResult.message}</>}
          <span className="ml-2 opacity-60">
            ({testResult.latency_ms}ms
            {testResult.http_status && ` · HTTP ${testResult.http_status}`})
          </span>
        </div>
      )}
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

function formatValidationTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatValidationStatus(
  s: ProviderStatus["last_validation_status"],
): string {
  if (s === "valid") return "✓ válida";
  if (s === "invalid") return "✗ inválida";
  if (s === "error") return "⚠ erro";
  return "—";
}
