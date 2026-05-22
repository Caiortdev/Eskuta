/**
 * Onboarding — primeira execução. Exige configurar pelo menos
 * 1 STT (Groq ou AssemblyAI) E 1 LLM (Claude/GPT/Gemini) antes de
 * liberar o app.
 *
 * Inteligente: se o usuário já tem ambas as categorias configuradas
 * no keyring, pula automaticamente pra Home (evita mostrar tela
 * desnecessária a cada visita manual em /onboarding).
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const STT_PROVIDERS = ["groq", "assemblyai"] as const;
const LLM_PROVIDERS = ["anthropic", "openai", "google"] as const;

type CheckState =
  | { kind: "checking" }
  | { kind: "incomplete"; hasStt: boolean; hasLlm: boolean }
  | { kind: "error"; message: string };

export function OnboardingPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<CheckState>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    api.keys
      .list()
      .then((res) => {
        if (cancelled) return;
        const configured = new Set(
          res.providers.filter((p) => p.is_configured).map((p) => p.provider),
        );
        const hasStt = STT_PROVIDERS.some((p) => configured.has(p));
        const hasLlm = LLM_PROVIDERS.some((p) => configured.has(p));
        if (hasStt && hasLlm) {
          // Skip — já tem o mínimo configurado
          navigate("/", { replace: true });
          return;
        }
        setState({ kind: "incomplete", hasStt, hasLlm });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? (err.detail ?? err.message)
            : err instanceof Error
              ? err.message
              : String(err);
        setState({ kind: "error", message: msg });
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (state.kind === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-background">
        <p className="text-sm text-muted-foreground">
          Verificando configuração…
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-background">
      <div className="w-full max-w-xl rounded-2xl border bg-card p-8 shadow-sm space-y-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-tight">
            Bem-vindo ao Eskuta
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Antes de gerar sua primeira ata, configure pelo menos uma chave de
            transcrição (Groq ou AssemblyAI) e uma de LLM (Claude, GPT ou
            Gemini).
          </p>
        </header>

        {state.kind === "incomplete" && (state.hasStt || state.hasLlm) && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs">
            ✓ <strong>Progresso:</strong>{" "}
            {state.hasStt ? "STT configurado ✓" : "STT pendente"} ·{" "}
            {state.hasLlm ? "LLM configurado ✓" : "LLM pendente"}
          </div>
        )}

        <ul className="space-y-2 text-sm">
          <li className="flex items-start gap-2">
            <span className="size-1.5 mt-2 rounded-full bg-primary" />
            <span>
              <strong>Transcrição (STT):</strong> Groq tem free tier generoso
              (recomendado). AssemblyAI também aceita 100h/mês grátis.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="size-1.5 mt-2 rounded-full bg-primary" />
            <span>
              <strong>LLM:</strong> Claude tem melhor qualidade pra ata. Gemini
              é o mais barato. GPT como alternativa.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="size-1.5 mt-2 rounded-full bg-primary" />
            <span>
              Suas keys ficam guardadas no keyring do sistema operacional —
              nunca em arquivo local.
            </span>
          </li>
        </ul>

        {state.kind === "error" && (
          <p className="text-xs text-destructive">
            Não consegui verificar suas configurações: {state.message}
          </p>
        )}

        <div className="flex gap-2 pt-2">
          <Button type="button" onClick={() => navigate("/settings")}>
            Configurar agora
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate("/")}>
            Pular por enquanto
          </Button>
        </div>
      </div>
    </div>
  );
}
