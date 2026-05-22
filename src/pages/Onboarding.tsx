/**
 * Onboarding — primeira execução. Exige configurar pelo menos
 * 1 STT (Groq ou AssemblyAI) E 1 LLM (Claude/GPT/Gemini) antes de
 * liberar o app. Esta rota é o gate inicial.
 */

import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function OnboardingPage() {
  const navigate = useNavigate();
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
